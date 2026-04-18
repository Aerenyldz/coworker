# Project Overview
This project is a FastAPI application that includes a backend and a static frontend.

# Requirements
- Python 3.11
- FastAPI
- Additional dependencies as specified in the requirements files.

# Setup (venv)
1. Create a virtual environment: `python -m venv .venv`
2. Activate the virtual environment:
   - On Windows: `.venv\Scripts\activate`
   - On macOS/Linux: `source .venv/bin/activate`

# Install
Install dependencies using pip:
```bash
pip install -r tenra_web/backend/requirements.txt
```

# Run (uvicorn)
To run the FastAPI backend, use:
```bash
uvicorn tenra_web.backend.server:app --reload
```

# Environment Variables
- `TENRA_ALLOWED_ORIGINS`: Set this environment variable to allow specific origins for CORS.

# Development (lint/test)
Use ruff for linting and pytest for running tests:
```bash
ruff check .
pytest
```

# Security Note
Avoid using `exec()` within your code where possible, as it can execute arbitrary code and pose security risks.