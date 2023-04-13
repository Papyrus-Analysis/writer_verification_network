import random

import cv2
import numpy as np
import torch
import torchvision.transforms
import torchvision.transforms
from PIL import ImageOps, Image
from torchvision.transforms import transforms, InterpolationMode

from utils.data_utils import resize_image, padding_image


def get_transforms(img_size):
    return torchvision.transforms.Compose([
        torchvision.transforms.RandomApply([
            torchvision.transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, hue=0.2),
        ], p=0.5),
        MovingResize((img_size, img_size), random_move=True),
        # torchvision.transforms.RandomApply([
        #     torchvision.transforms.RandomRotation(degrees=15, fill=255, interpolation=InterpolationMode.BICUBIC),
        # ], p=0.6),
        RandomResize(img_size),
        # RandomCutOut(mask_size=int(img_size // 3.5), mask_color=(255, 255, 255), p=0.5),
        # torchvision.transforms.RandomApply([
        #     torchvision.transforms.GaussianBlur(3, sigma=(1, 2)),
        # ], p=0.5),
        # torchvision.transforms.RandomHorizontalFlip(),
        torchvision.transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])


def val_transforms(img_size):
    return torchvision.transforms.Compose([
        MovingResize((img_size, img_size), random_move=False),
        torchvision.transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])


class UnNormalize(torchvision.transforms.Normalize):
    def __init__(self,mean,std,*args,**kwargs):
        new_mean = [-m/s for m,s in zip(mean,std)]
        new_std = [1/s for s in std]
        super().__init__(new_mean, new_std, *args, **kwargs)


def reverse_transform():
    return torchvision.transforms.Compose([
        UnNormalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        torchvision.transforms.ToPILImage(),
        lambda image: ImageOps.invert(image)
    ])


class MovingResize:
    def __init__(self, img_size, random_move=True):
        self.img_width, self.img_height = img_size
        self.random_move = random_move

    def __call__(self, img):
        mov = 0.5 if not self.random_move else random.randint(0, 100) / 100.
        width, height = img.size
        ratio_w = self.img_width / width
        ratio_h = self.img_height / height
        scale = min(ratio_h, ratio_w)
        image = resize_image(img, scale).convert('RGB')
        width, height = image.size
        # Find the dominant color
        # dominant_color = bincount_app(np.asarray(img.convert("RGB")))
        # Add image to the background
        result = Image.new(mode="RGB", size=(self.img_width, self.img_height), color=(255, 255, 255))
        result.paste(image, box=(int(mov * (self.img_width - width)), int(mov * (self.img_height - height))))
        return result


class RandomResize:
    def __init__(self, im_size, p=0.5, threshold=(0.8, 1.2)):
        self.p = p
        self.threshold = threshold
        self.im_size = im_size
        self.cropper = torchvision.transforms.RandomCrop(im_size)

    def __call__(self, img):
        if self.p < torch.rand(1):
            return img

        factor = random.randint(int(self.threshold[0] * 10), int(self.threshold[1] * 10)) / 10.
        new_img = resize_image(img, factor).convert('RGB')
        if new_img.width > self.im_size:
            return self.cropper(new_img)
        mov_w = random.randint(0, 100) / 100.
        mov_h = random.randint(0, 100) / 100.

        result = Image.new(mode="RGB", size=(self.im_size, self.im_size), color=(255, 255, 255))
        result.paste(new_img, box=(int(mov_w * (self.im_size - new_img.width)),
                                   int(mov_h * (self.im_size - new_img.height))))
        return result


def cutout(image, mask_size, p, cutout_inside, mask_color=(0, 0, 0)):
    mask_size_half = mask_size // 2
    offset = 1 if mask_size % 2 == 0 else 0
    image = np.asarray(image).copy()

    if np.random.random() > p:
        return image

    h, w = image.shape[:2]

    if cutout_inside:
        cxmin, cxmax = mask_size_half, w + offset - mask_size_half
        cymin, cymax = mask_size_half, h + offset - mask_size_half
    else:
        cxmin, cxmax = 0, w + offset
        cymin, cymax = 0, h + offset

    cx = np.random.randint(cxmin, cxmax)
    cy = np.random.randint(cymin, cymax)
    xmin = cx - mask_size_half
    ymin = cy - mask_size_half
    xmax = xmin + mask_size
    ymax = ymin + mask_size
    xmin = max(0, xmin)
    ymin = max(0, ymin)
    xmax = min(w, xmax)
    ymax = min(h, ymax)
    image[ymin:ymax, xmin:xmax] = mask_color
    return image


class RandomCutOut:

    def __init__(self, mask_size, p=0.5, mask_color=(0, 0, 0)):
        self.mask_size = mask_size
        self.p = p
        self.mask_color = mask_color

    def __call__(self, image):
        out_img = cutout(image, self.mask_size, self.p, True, self.mask_color)
        return Image.fromarray(out_img)


class RandomBinarizeThreshold:
    def __call__(self, img, sample_size=10):
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        w, h = gray.shape
        top_left = gray[0:sample_size, 0:sample_size]
        top_right = gray[w - sample_size:w, 0:sample_size]
        bot_left = gray[0:sample_size, h-sample_size:h]
        bot_right = gray[w - sample_size:w, h-sample_size:h]

        top_left = np.min(top_left), np.max(top_left)
        top_right = np.min(top_right), np.max(top_right)
        bot_left = np.min(bot_left), np.max(bot_left)
        bot_right = np.min(bot_right), np.max(bot_right)

        candidates = sorted([top_left, top_right, bot_left, bot_right], key=lambda x: x[1], reverse=True)
        min_threshold, max_threshold = candidates[0]

        img[gray > min_threshold] = 255
        return img
