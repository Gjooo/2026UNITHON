"""Stable Diffusion 1.5 UNet에 LoRA 어댑터를 짧게 학습한다.

데모용이므로 목표는 좋은 모델이 아니라 **10분 안에 끝나는 진짜 GPU 학습**이다.
학습 데이터는 외부 데이터셋을 받지 않고 그 자리에서 만든다. 데모가 네트워크
상태나 데이터셋 라이선스에 의존하지 않게 하기 위해서다.

환경변수:
    TRAINING_STEPS  학습 스텝 수 (기본 200)
    OUTPUT_DIR      LoRA 가중치를 저장할 경로

주의: 이 스크립트는 GPU에서 아직 실행 검증되지 않았다. 실제 GPU에서 한 번
돌려본 뒤에 데모 프로필의 실행 명령으로 채택한다. 검증 전에는
`TRAINING_COMMAND` 로 다른 명령을 지정해 컨테이너 왕복만 확인할 수 있다.
"""

from __future__ import annotations

import math
import os
import random
import sys
import time

import torch
import torch.nn.functional as F
from diffusers import AutoencoderKL, DDPMScheduler, UNet2DConditionModel
from peft import LoraConfig, get_peft_model
from transformers import CLIPTextModel, CLIPTokenizer

MODEL_ID = "stable-diffusion-v1-5/stable-diffusion-v1-5"
RESOLUTION = 512
BATCH_SIZE = 1
LEARNING_RATE = 1e-4
PROMPT = "a photo of a sks geometric emblem"


def synthetic_batch(count: int, device: torch.device) -> torch.Tensor:
    """단순한 도형 이미지를 만들어 학습 대상으로 쓴다."""

    images = torch.zeros(count, 3, RESOLUTION, RESOLUTION, device=device)
    for index in range(count):
        color = torch.rand(3, device=device).view(3, 1, 1)
        images[index] = color * 0.35
        size = random.randint(RESOLUTION // 6, RESOLUTION // 3)
        top = random.randint(0, RESOLUTION - size)
        left = random.randint(0, RESOLUTION - size)
        patch_color = torch.rand(3, device=device).view(3, 1, 1)
        images[index, :, top : top + size, left : left + size] = patch_color
    # VAE 입력 범위로 정규화한다.
    return images * 2.0 - 1.0


def main() -> int:
    if not torch.cuda.is_available():
        print("CUDA를 사용할 수 없습니다. GPU 인스턴스에서 실행해야 합니다.", file=sys.stderr)
        return 2

    steps = int(os.getenv("TRAINING_STEPS", "200"))
    output_dir = os.getenv("OUTPUT_DIR", "/workspace/output")
    device = torch.device("cuda")
    dtype = torch.float16

    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"학습 스텝: {steps}")

    tokenizer = CLIPTokenizer.from_pretrained(MODEL_ID, subfolder="tokenizer")
    # 이미지에는 fp16 파일만 들어 있다. 얼려 두는 두 부품은 fp16으로 그대로 쓰고,
    # 학습하는 UNet만 fp32로 올려 짧은 학습에서 손실이 발산하지 않게 한다.
    text_encoder = CLIPTextModel.from_pretrained(
        MODEL_ID, subfolder="text_encoder", variant="fp16", torch_dtype=dtype
    ).to(device)
    vae = AutoencoderKL.from_pretrained(
        MODEL_ID, subfolder="vae", variant="fp16", torch_dtype=dtype
    ).to(device)
    unet = UNet2DConditionModel.from_pretrained(
        MODEL_ID, subfolder="unet", variant="fp16", torch_dtype=torch.float32
    ).to(device)
    scheduler = DDPMScheduler.from_pretrained(MODEL_ID, subfolder="scheduler")

    text_encoder.requires_grad_(False)
    vae.requires_grad_(False)

    # UNet의 attention 투영에만 LoRA를 붙인다. 짧은 학습에서 가장 효과가 크다.
    unet = get_peft_model(
        unet,
        LoraConfig(r=4, lora_alpha=4, target_modules=["to_q", "to_k", "to_v", "to_out.0"]),
    )
    unet.print_trainable_parameters()

    trainable = [p for p in unet.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=LEARNING_RATE)

    tokens = tokenizer(
        [PROMPT] * BATCH_SIZE,
        padding="max_length",
        max_length=tokenizer.model_max_length,
        truncation=True,
        return_tensors="pt",
    ).input_ids.to(device)
    with torch.no_grad():
        encoder_hidden_states = text_encoder(tokens)[0]

    started = time.time()
    unet.train()
    for step in range(1, steps + 1):
        images = synthetic_batch(BATCH_SIZE, device).to(dtype)
        with torch.no_grad():
            latents = vae.encode(images).latent_dist.sample() * vae.config.scaling_factor
        latents = latents.float()

        noise = torch.randn_like(latents)
        timesteps = torch.randint(
            0, scheduler.config.num_train_timesteps, (latents.shape[0],), device=device
        ).long()
        noisy = scheduler.add_noise(latents, noise, timesteps)

        predicted = unet(noisy, timesteps, encoder_hidden_states.float()).sample
        loss = F.mse_loss(predicted, noise)

        loss.backward()
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)

        if step % 10 == 0 or step == steps:
            elapsed = time.time() - started
            print(f"step {step}/{steps} loss={loss.item():.4f} elapsed={elapsed:.0f}s")

        if not math.isfinite(loss.item()):
            print("손실이 발산했습니다.", file=sys.stderr)
            return 1

    os.makedirs(output_dir, exist_ok=True)
    unet.save_pretrained(output_dir)
    print(f"LoRA 가중치를 저장했습니다: {output_dir}")
    print(f"Training completed. {steps}/{steps} steps.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
