# 백엔드가 선택한 GPU에서 이 이미지 하나만 실행된다.
# 실행 명령은 백엔드 상수이며 컨테이너는 완료 결과를 반드시 백엔드에 알린다.
FROM pytorch/pytorch:2.4.0-cuda12.4-cudnn9-runtime

ENV PYTHONUNBUFFERED=1 \
    HF_HOME=/workspace/.cache/huggingface \
    TRAINING_STEPS=200 \
    OUTPUT_DIR=/workspace/output

WORKDIR /workspace

# 학습 의존성은 이미지에 고정한다. 실행 시점에 설치하면 10분 상한을 까먹는다.
RUN pip install --no-cache-dir \
      diffusers==0.31.0 \
      transformers==4.46.3 \
      peft==0.13.2 \
      accelerate==1.1.1 \
      safetensors==0.4.5

# 백엔드의 start_command 가 `./run-demo-training.sh` 를 호출하므로
# 스크립트는 WORKDIR 에 실행 가능한 상태로 있어야 한다.
COPY run-demo-training.sh report_completion.py train_sd15_lora.py ./
RUN chmod +x run-demo-training.sh && mkdir -p "$OUTPUT_DIR"

# 모델 가중치를 미리 받아 둔다. 데모 중 다운로드에 시간을 쓰지 않기 위해서다.
# 실제로 쓰는 세 부품의 fp16 파일만 받는다. 전체를 받으면 이미지가 몇 GB 커지고
# 그만큼 Pod 시작 시 image pull 이 길어져 최대 실행시간을 까먹는다.
RUN python3 -c "\
from huggingface_hub import snapshot_download; \
snapshot_download('stable-diffusion-v1-5/stable-diffusion-v1-5', allow_patterns=[ \
  'model_index.json', 'tokenizer/*', 'scheduler/*', \
  'text_encoder/config.json', 'text_encoder/model.fp16.safetensors', \
  'vae/config.json', 'vae/diffusion_pytorch_model.fp16.safetensors', \
  'unet/config.json', 'unet/diffusion_pytorch_model.fp16.safetensors'])"

CMD ["./run-demo-training.sh"]
