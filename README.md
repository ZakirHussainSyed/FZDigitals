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

## SSO Authentication Setup

The website supports Single Sign-On (SSO) with Google OAuth. To enable SSO:

### Google OAuth Setup

1. **Create a Google Cloud Project:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing one
   - Enable Google+ API

2. **Configure OAuth 2.0 Credentials:**
   - Go to APIs & Services → Credentials
   - Create OAuth 2.0 Client ID
   - Application type: Web application
   - Authorized redirect URIs:
     - Local: `http://127.0.0.1:8000/accounts/google/login/callback/`
     - Production: `https://yourdomain.com/accounts/google/login/callback/`

3. **Add Environment Variables:**
   Add these to your environment or `.env` file:
   ```bash
   SOCIAL_AUTH_GOOGLE_OAUTH2_KEY=your_google_client_id
   SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET=your_google_client_secret
   ```

4. **Configure Django Admin:**
   - Run `python3 manage.py createsuperuser`
   - Go to http://localhost:8000/admin/
   - Navigate to Sites → Set domain to your domain (e.g., `127.0.0.1:8000`)
   - Navigate to Social Applications → Add Google OAuth2 app with your credentials

### Production Deployment
Use the provided `start.sh` script for production deployment on Render:
```bash
bash start.sh
``` 
