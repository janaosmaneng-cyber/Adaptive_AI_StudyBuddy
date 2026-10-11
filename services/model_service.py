import threading
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from config import LLM_NAME, EMB_NAME, QUANT

print(f"[AdaptiveAI] Loading language model: {LLM_NAME} ({QUANT})")
tokenizer = AutoTokenizer.from_pretrained(LLM_NAME)

model_options = {"device_map": "auto"}

# if QUANT == "4bit":
#     if not torch.cuda.is_available():
#         raise RuntimeError(
#             "4-bit bitsandbytes loading normally requires a compatible CUDA GPU. "
#             "Use a supported GPU environment or select a compatible local model runtime."
#         )
#     model_options["quantization_config"] = BitsAndBytesConfig(
#         load_in_4bit=True,
#         bnb_4bit_quant_type="nf4",
#         bnb_4bit_compute_dtype=torch.float16,
#         bnb_4bit_use_double_quant=True,
#     )


if QUANT == "4bit":
    if not torch.cuda.is_available():
        raise RuntimeError(
            "4-bit loading requires CUDA. "
            "Check your PyTorch and GPU setup."
        )

    model_options["quantization_config"] = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )
    model_options["torch_dtype"] = torch.float16
    model_options["device_map"] = "auto"

elif QUANT == "8bit":
    if not torch.cuda.is_available():
        raise RuntimeError(
            "8-bit bitsandbytes loading normally requires a compatible CUDA GPU."
        )
    model_options["quantization_config"] = BitsAndBytesConfig(load_in_8bit=True)
elif QUANT == "fp16":
    model_options["torch_dtype"] = torch.float16
else:
    raise ValueError("QUANT must be '4bit', '8bit', or 'fp16'.")

llm = AutoModelForCausalLM.from_pretrained(LLM_NAME, **model_options)
llm.eval()

print(f"[AdaptiveAI] Loading embedding model: {EMB_NAME}")
embedder = SentenceTransformer(EMB_NAME)

# Avoid overlapping generate() calls on a single loaded model.
generation_lock = threading.Lock()

def generate_text(messages, max_new_tokens=400, temperature=0.3):
    """Generate a reply from chat messages and return only newly generated tokens."""
    with generation_lock:
        inputs = tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True,
        ).to(llm.device)

        generation_options = {
            "max_new_tokens": max_new_tokens,
            "pad_token_id": tokenizer.eos_token_id,
        }

        if temperature > 0:
            generation_options.update(
                do_sample=True,
                temperature=temperature,
                top_p=0.95,
            )
        else:
            generation_options["do_sample"] = False

        with torch.inference_mode():
            output = llm.generate(**inputs, **generation_options)

        new_tokens = output[0][inputs["input_ids"].shape[1]:]
        return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

def model_memory_footprint_gb():
    """Approximate model parameter/buffer footprint; not total GPU process usage."""
    return round(llm.get_memory_footprint() / (1024 ** 3), 2)
