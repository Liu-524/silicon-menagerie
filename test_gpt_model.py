import math
from gpt_utils import load_model, generate_images_freely, generate_images_from_half
from torchvision.utils import save_image

# load gpt & vq (encoder-decoder) models
model_name = 'y_gimel'
gpt_model, vq_model = load_model(model_name)


# # ========== GENERATE UNCONDITIONAL SAMPLES ==========
# n_samples = 25  # total number of samples to generate

# x = generate_images_freely(gpt_model, vq_model, n_samples=n_samples)

# # save generated images
# save_image(x, "free_samples_from_{}.png".format(model_name), nrow=int(math.sqrt(n_samples)), padding=1, normalize=True)
# # ============================================================


# ========== GENERATE CONDITIONAL SAMPLES ==========
n_imgs = 12            # number of images to condition on
n_samples_per_img = 2  # number of conditional samples per image
seed = 1
img_dir = '/vast/eo41/data/konkle_iid/val'  # replace this with desired data directory (we will use random images from this directory to condition on)

x = generate_images_from_half(gpt_model, vq_model, img_dir, n_imgs=n_imgs, n_samples_per_img=n_samples_per_img, seed=seed)

# save generated images
save_image(x, "conditional_samples_from_{}_{}.png".format(model_name, seed), nrow=n_imgs, padding=0, normalize=True)
# ============================================================