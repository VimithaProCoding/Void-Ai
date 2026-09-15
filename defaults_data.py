#using for settings restores.

def get_default_apidata():
    """Returns default API provider and model catalog data (matching apidata.json)."""
    return {
        "version": 1,
        "providers": {
            "Groq AI": {
                "base_url": "https://api.groq.com/openai/v1",
                "env_key": "GROQ_API_KEY"
            },
            "OpenRouter": {
                "base_url": "https://openrouter.ai/api/v1",
                "env_key": "OPENROUTER_API_KEY"
            },
            "Ollama Cloud": {
                "base_url": "http://localhost:11434/v1",
                "env_key": "OLLAMA_API_KEY"
            }
        },
        "roles": {
            "Fast": [
                {
                    "provider": "Groq AI",
                    "model_id": "openai/gpt-oss-20b",
                    "model_name": "GPT OSS 20B",
                    "default": True
                },
                {
                    "provider": "Groq AI",
                    "model_id": "groq/compound-mini",
                    "model_name": "Compound Mini",
                    "default": False
                },
                {
                    "provider": "OpenRouter",
                    "model_id": "liquid/lfm-2.5-2.6b:free",
                    "model_name": "Liquid LFM 2.6B",
                    "default": False
                }
            ],
            "Flash": [
                {
                    "provider": "Groq AI",
                    "model_id": "qwen/qwen3.6-27b",
                    "model_name": "Qwen 3.6 27B",
                    "default": True
                },
                {
                    "provider": "OpenRouter",
                    "model_id": 'liquid/lfm-2.5-2.6b:free',
                    "model_name": "Liquid LFM 2.6B",
                    "default": False
                },
                {
                    "provider": "OpenRouter",
                    "model_id": "cohere/north-mini-code:free",
                    "model_name": "Cohere North Mini Code",
                    "default": False
                }
            ],
            "Complex": [
                {
                    "provider": "Groq AI",
                    "model_id": "openai/gpt-oss-120b",
                    "model_name": "GPT OSS 120B",
                    "default": True
                },
                {
                    "provider": "OpenRouter",
                    "model_id": "nvidia/nemotron-3-ultra-550b-a55b:free",
                    "model_name": "NVIDIA Nemotron 3 Ultra",
                    "default": False
                },
                {
                    "provider": "OpenRouter",
                    "model_id": "nvidia/nemotron-3.5-lightning:free",
                    "model_name": "NVIDIA Nemotron 3.5 Lightning",
                    "default": False
                }
            ]
        },
        "models": {
            "Groq AI": [
                {
                    "model_id": "openai/gpt-oss-20b",
                    "model_name": "GPT OSS 20B",
                    "provider": "Groq AI",
                    "default": True
                },
                {
                    "model_id": "groq/compound-mini",
                    "model_name": "Compound Mini",
                    "provider": "Groq AI",
                    "default": False
                },
                {
                    "model_id": "openai/gpt-oss-120b",
                    "model_name": "GPT OSS 120B",
                    "provider": "Groq AI",
                    "default": False
                }
            ],
            "OpenRouter": [
                {
                    "model_id": "liquid/lfm-2.5-2.6b:free",
                    "model_name": "Liquid LFM 2.6B",
                    "provider": "OpenRouter",
                    "default": True
                },
                {
                    "model_id": "cohere/north-mini-code:free",
                    "model_name": "Cohere North Mini Code",
                    "provider": "OpenRouter",
                    "default": False
                },
                {
                    "model_id": "nvidia/nemotron-3-ultra-550b-a55b:free",
                    "model_name": "NVIDIA Nemotron 3 Ultra",
                    "provider": "OpenRouter",
                    "default": False
                },
                {
                    "model_id": "nvidia/nemotron-3.5-lightning:free",
                    "model_name": "NVIDIA Nemotron 3.5 Lightning",
                    "provider": "OpenRouter",
                    "default": False
                }
            ],
            "Ollama Cloud": []
        }
    }


def get_default_appdata():
    """Returns default application state, theme, and active model mapping."""
    return {
        "THEMES": {
            "Neon Purple": {
                "hex": "#9D4EDD",
                "grad_start": "#C77DFF",
                "grad_end": "#5A189A"
            },
            "Royal Gold": {
                "hex": "#D4AF37",
                "grad_start": "#F3E5AB",
                "grad_end": "#996515"
            },
            "Emerald Green": {
                "hex": "#00C853",
                "grad_start": "#69F0AE",
                "grad_end": "#007E33"
            },
            "Velvet Rose": {
                "hex": "#FF4D6D",
                "grad_start": "#FF758F",
                "grad_end": "#A4133C"
            }
        },
        "APP_STATE": {
            "font_size": 13,
            "bg_animation": True,
            "stream_text": True,
            "model_themes": {
                "Fast": "Neon Purple",
                "Flash": "Emerald Green",
                "Complex": "Velvet Rose"
            },
            "selected_model_role": "Flash",
            "auto_load_recent_chat": False,
            "developer_options": False,
            "last_chat_id": None,
            "groq_api_keys_url": "https://console.groq.com/keys"
        },
        "MODEL_CONFIGS": {
            "Fast": {
                "provider": "Groq AI",
                "model": "openai/gpt-oss-20b"
            },
            "Flash": {
                "provider": "OpenRouter",
                "model": "liquid/lfm-2.5-2.6b:free"
            },
            "Complex": {
                "provider": "OpenRouter",
                "model": "nvidia/nemotron-3-ultra-550b-a55b:free"
            }
        }
}