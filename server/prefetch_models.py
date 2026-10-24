"""Download the model weights into the local caches (HF_HOME / MODELSCOPE_CACHE) so the server can start offline.
Run once on a machine with internet, then copy the cache directories to the air-gapped host, or use
`docker build --build-arg PREFETCH=1`.  Set AWAAZ_WHISPER / AWAAZ_E2V to prefetch other models."""
import os

whisper = os.environ.get("AWAAZ_WHISPER", "large-v3-turbo")
e2v = os.environ.get("AWAAZ_E2V", "iic/emotion2vec_plus_base")

from faster_whisper.utils import download_model  # noqa: E402

print("whisper:", download_model(whisper))
from modelscope import snapshot_download  # noqa: E402

print("emotion2vec:", snapshot_download(e2v))
