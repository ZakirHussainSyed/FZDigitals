# FZDigitals
FZDigitals Advertisement

## Local Development

### Prerequisites
- Python 3.8+
- pip

### Setup

1. **Install dependencies:**
   ```bash
   python3 -m pip install -r requirements.txt
   ```

2. **Run database migrations:**
   ```bash
   python3 manage.py migrate
   ```

3. **Start the development server:**
   ```bash
   python3 manage.py runserver
   ```

4. **Access the website:**
   Open your browser to http://localhost:8000

### Production Deployment
Use the provided `start.sh` script for production deployment on Render:
```bash
bash start.sh
``` 
