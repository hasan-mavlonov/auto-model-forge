# AutoModel Forge

AutoModel Forge is a Django-based web platform for creating and managing **LoRA model training jobs**, provisioning GPUs via **RunPod**, and handling **payments** for training.

## Features
- User accounts: registration, login, email flow  
- Training jobs: upload images, configure LoRA, track status  
- RunPod integration: GPU selection and pod orchestration  
- Payments: Stripe flow and webhook handling  
- Admin tools: staff training job dashboard  
- Static & media handling via WhiteNoise  

## Project Structure

AutoModel_Forge/
- AutoModel_Forge/ — project settings and main URLs  
- accounts/ — authentication and user management  
- core/ — landing and core pages  
- training/ — training jobs, RunPod client, tasks  
- payments/ — Stripe integration and webhooks  
- templates/ — HTML templates  
- static/ — static assets  
- media/ — training images and trained models  
- manage.py  
- requirements.txt  

## Tech Stack
- Python 3.13  
- Django 5.2  
- PostgreSQL (or SQLite fallback)  
- RunPod API  
- Stripe  
- Gunicorn + WhiteNoise  

## Environment Variables

Create a `.env` file (see `.env_example`):

SECRET_KEY=django-insecure-...  
DEBUG=True  
DATABASE_URL=postgresql://...  

RUNPOD_API_KEY=...  
RUNPOD_POD_TEMPLATE_ID=...  
RUNPOD_DEFAULT_GPU=NVIDIA_L4  
RUNPOD_GPU_PREFERENCES=NVIDIA_L4,NVIDIA_A10G,NVIDIA_3090,NVIDIA_4090,NVIDIA_A100  

LORA_DEFAULT_STEPS=2000  
LORA_DEFAULT_LEARNING_RATE=0.0001  
LORA_TRAIN_TEXT_ENCODER=False  

USD_TO_CNY_RATE=7.2  

## How to Start the Project (Local)

1. Clone the repository  
git clone <your-repo-url>  
cd AutoModel_Forge  

2. Create and activate virtual environment  
python -m venv .venv  
source .venv/bin/activate  

3. Install dependencies  
pip install -r requirements.txt  

4. Apply migrations  
python manage.py migrate  

5. Create admin user (optional)  
python manage.py createsuperuser  

6. Run the development server  
python manage.py runserver  

The app will be available at:  
http://127.0.0.1:8000/

## Main Routes
- Home: /  
- Accounts: /accounts/  
- Training: /train/  
- Payments: /payments/  
- Admin: /admin/  
- Staff jobs: /admin-jobs/  

## Notes
- Uploaded data and trained models are stored in `media/`  
- SQLite is used if `DATABASE_URL` is not provided  
- Designed to be production-ready with PostgreSQL  

## License
MIT
