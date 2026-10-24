# AwaazAlert analysis server (GPU). NOT build-tested on the author's machine (no Docker there): treat the first
# build as part of your acceptance test. See docs/DEPLOYMENT.md.
#
#   docker build -t awaazalert:0.2 .                  # models download on first start (needs internet once)
#   docker build --build-arg PREFETCH=1 -t awaazalert:0.2 .   # bake the models in (for air-gapped networks)
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-pip ffmpeg libsndfile1 tini ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 awaaz && mkdir -p /data /models && chown awaaz:awaaz /data /models
WORKDIR /app

COPY server/requirements.txt server/requirements.txt
RUN python3 -m pip install -r server/requirements.txt

COPY server/ server/

ENV HF_HOME=/models/hf MODELSCOPE_CACHE=/models/modelscope AWAAZ_DATA_DIR=/data AWAAZ_MODE=production
ARG PREFETCH=0
RUN if [ "$PREFETCH" = "1" ]; then python3 server/prefetch_models.py; fi && chown -R awaaz:awaaz /models

USER awaaz
VOLUME ["/data"]
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
  CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/ready', timeout=4).status == 200 else 1)"

ENTRYPOINT ["tini", "--"]
CMD ["python3", "server/main.py"]
