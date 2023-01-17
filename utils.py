"""
Util functions
"""
import os
import sys
import torch
from huggingface_hub import hf_hub_download

def load_model(model_name):

    # parse identifier
    alg, data, model_spec = model_name.split("_")

    # checks
    assert alg in ["dino", "mugs", "mae"], "Unrecognized algorithm!"
    assert data in ["say", "sfp", "s", "a", "y", "imagenet100", "imagenet10", "imagenet3", "imagenet1"], "Unrecognized data!"
    assert model_spec in ["resnext50", "vitb14", "vitl16", "vitb16", "vits16"], "Unrecognized architecture!"

    if model_spec == "resnext50":
        arch, patch_size = "resnext50_32x4d", None
    elif model_spec == "vitb14":
        arch, patch_size = "vit_base", 14
    elif model_spec == "vitl16":
        arch, patch_size = "vit_large", 16
    elif model_spec == "vitb16":
        arch, patch_size = "vit_base", 16
    elif model_spec == "vits16":
        arch, patch_size = "vit_small", 16

    # download checkpoint from hf
    checkpoint = hf_hub_download(repo_id="eminorhan/"+model_name, filename=model_name+".pth")

    if alg == "dino" or alg == "mugs":
        model = build_dino_mugs(arch, patch_size)
        load_dino_mugs(model, checkpoint, "teacher")
    elif alg == "mae":
        model = build_mae(arch, patch_size)
        load_mae(model, checkpoint)

    return model

def load_dino_mugs(model, pretrained_weights, checkpoint_key):
    if os.path.isfile(pretrained_weights):
        state_dict = torch.load(pretrained_weights, map_location="cpu")
        if checkpoint_key is not None and checkpoint_key in state_dict:
            print(f"Take key {checkpoint_key} in provided checkpoint dict")
            state_dict = state_dict[checkpoint_key]

        # remove `module.` prefix
        state_dict = {k.replace("module.", ""): v for k, v in state_dict.items()}
        # remove `backbone.` prefix induced by multicrop wrapper
        state_dict = {k.replace("backbone.", ""): v for k, v in state_dict.items()}
        # remove `encoder.` prefix if it exists
        state_dict = {k.replace("encoder.", ""): v for k, v in state_dict.items()}

        msg = model.load_state_dict(state_dict, strict=False)
        print('Pretrained weights found at {} and loaded with msg: {}'.format(pretrained_weights, msg))
    else:
        print("There is no reference weights available for this model => We use random weights.")

def build_dino_mugs(arch, patch_size):
    import vision_transformer_dino_mugs as vits
    from torchvision import models as torchvision_models

    # if the network is a Vision Transformer (i.e. vit_tiny, vit_small, vit_base, vit_large)
    if arch in vits.__dict__.keys():
        model = vits.__dict__[arch](patch_size=patch_size, num_classes=0)
    # otherwise, we check if the architecture is in torchvision models
    elif arch in torchvision_models.__dict__.keys():
        model = torchvision_models.__dict__[arch]()
        model.fc = torch.nn.Identity()
    else:
        print(f"Unknown architecture: {arch}")
        sys.exit(1)

    return model

def build_mae(arch, patch_size):
    import vision_transformer_mae as vits
    full_model_name = arch + "_patch" + str(patch_size)
    model = vits.__dict__[full_model_name](num_classes=0, global_pool=False)

    return model

def load_mae(model, pretrained_weights):
    if os.path.isfile(pretrained_weights):    
        checkpoint = torch.load(pretrained_weights, map_location='cpu')
        checkpoint_model = checkpoint['model']

        # interpolate position embedding
        interpolate_pos_embed(model, checkpoint_model)

        # load pre-trained model
        msg = model.load_state_dict(checkpoint_model, strict=False)
        print('Pretrained weights found at {} and loaded with msg: {}'.format(pretrained_weights, msg))
    else:
        print("There is no reference weights available for this model => We use random weights.")

def interpolate_pos_embed(model, checkpoint_model):
    '''
    Interpolate position embeddings for high-resolution. 
    Reference: https://github.com/facebookresearch/deit
    '''
    if 'pos_embed' in checkpoint_model:
        pos_embed_checkpoint = checkpoint_model['pos_embed']
        embedding_size = pos_embed_checkpoint.shape[-1]
        num_patches = model.patch_embed.num_patches
        num_extra_tokens = model.pos_embed.shape[-2] - num_patches
        # height (== width) for the checkpoint position embedding
        orig_size = int((pos_embed_checkpoint.shape[-2] - num_extra_tokens) ** 0.5)
        # height (== width) for the new position embedding
        new_size = int(num_patches ** 0.5)
        # class_token and dist_token are kept unchanged
        if orig_size != new_size:
            print("Position interpolate from %dx%d to %dx%d" % (orig_size, orig_size, new_size, new_size))
            extra_tokens = pos_embed_checkpoint[:, :num_extra_tokens]
            # only the position tokens are interpolated
            pos_tokens = pos_embed_checkpoint[:, num_extra_tokens:]
            pos_tokens = pos_tokens.reshape(-1, orig_size, orig_size, embedding_size).permute(0, 3, 1, 2)
            pos_tokens = torch.nn.functional.interpolate(
                pos_tokens, size=(new_size, new_size), mode='bicubic', align_corners=False)
            pos_tokens = pos_tokens.permute(0, 2, 3, 1).flatten(1, 2)
            new_pos_embed = torch.cat((extra_tokens, pos_tokens), dim=1)
            checkpoint_model['pos_embed'] = new_pos_embed

def preprocess_image(image_path, image_size):
    from PIL import Image
    from torchvision import transforms as pth_transforms

    # open image
    if image_path is None:
        import requests
        from io import BytesIO
        # user has not specified any image - we use an image from the DINO repo
        print("Since no image path have been provided, we take the first image in our paper.")
        response = requests.get("https://dl.fbaipublicfiles.com/dino/img.png")
        img = Image.open(BytesIO(response.content))
        img = img.convert('RGB')
    elif os.path.isfile(image_path):
        with open(image_path, 'rb') as f:
            img = Image.open(f)
            img = img.convert('RGB')
    else:
        print(f"Provided image path {image_path} is non valid.")
        sys.exit(1)

    transform = pth_transforms.Compose([
        pth_transforms.Resize(image_size),
        pth_transforms.ToTensor(),
        pth_transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225)),
    ])
    img = transform(img)

    return img

def visualize_attentions(model, img, patch_size, save_name="atts", device=torch.device("cpu"), threshold=None):
    from torch.nn.functional import interpolate
    from torchvision.utils import save_image
    import random, colorsys

    def random_colors(N, bright=True):
        """
        Generate random colors.
        """
        brightness = 1.0 if bright else 0.7
        hsv = [(i / N, 1, brightness) for i in range(N)]
        colors = list(map(lambda c: colorsys.hsv_to_rgb(*c), hsv))
        random.shuffle(colors)
        return colors

    # make the image divisible by the patch size
    print(img.shape)
    w, h = img.shape[1] - img.shape[1] % patch_size, img.shape[2] - img.shape[2] % patch_size
    img = img[:, :w, :h].unsqueeze(0)

    w_featmap = img.shape[-2] // patch_size
    h_featmap = img.shape[-1] // patch_size

    attentions = model.get_last_selfattention(img.to(device))

    nh = attentions.shape[1]  # number of heads

    # we keep only the output patch attention (cls token)
    attentions = attentions[0, :, 0, 1:].reshape(nh, -1)

    if threshold is not None:
        # thresholded attention maps: we keep only a certain percentage of the mass
        val, idx = torch.sort(attentions)
        val /= torch.sum(val, dim=1, keepdim=True)
        cumval = torch.cumsum(val, dim=1)
        th_attn = cumval > (1 - threshold)
        idx2 = torch.argsort(idx)
        for head in range(nh):
            th_attn[head] = th_attn[head][idx2[head]]
        th_attn = th_attn.reshape(nh, w_featmap, h_featmap).float()
        # interpolate
        attentions = interpolate(th_attn.unsqueeze(0), scale_factor=patch_size, mode="nearest")[0].cpu().numpy()
    else: 
        attentions = attentions.reshape(nh, w_featmap, h_featmap)
        attentions = interpolate(attentions.unsqueeze(0), scale_factor=patch_size, mode="nearest")[0].cpu().numpy()
    
    abs_attentions = torch.from_numpy(abs(attentions))
    colors = random_colors(nh, bright=True)
    new_attentions = torch.zeros(nh, 3, w, h)
    for i in range(nh):
        new_attentions[i, 0, :, :] = colors[i][0] * torch.from_numpy(attentions[i, :, :])
        new_attentions[i, 1, :, :] = colors[i][1] * torch.from_numpy(attentions[i, :, :])
        new_attentions[i, 2, :, :] = colors[i][2] * torch.from_numpy(attentions[i, :, :])

    combined_map = torch.zeros(1, 3, w, h)
    for i in range(w):
        for j in range(h):
            max_ind  = torch.argmax(abs_attentions[:, i, j])
            combined_map[0, 0, i, j] = new_attentions[max_ind, 0, i, j]
            combined_map[0, 1, i, j] = new_attentions[max_ind, 1, i, j]
            combined_map[0, 2, i, j] = new_attentions[max_ind, 2, i, j]

    display_tensor = torch.cat((img, new_attentions))
    display_tensor_combined = torch.cat((img, combined_map))

    print('Display tensor shape:', display_tensor.shape)
    print('Display tensor combined shape:', display_tensor_combined.shape)

    # TODO: handle the layout better
    save_image(display_tensor, save_name, nrow=4, padding=0, normalize=True, scale_each=True)
    save_image(display_tensor_combined, "combined_" + save_name, nrow=2, padding=0, normalize=True, scale_each=True)