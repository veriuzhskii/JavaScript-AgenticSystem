# Javascript Learning System
This is a multi-agent system designed to help users learn JavaScript in an interactive, chatbot-like environment. The system consists of specialized AI agents that work together to provide explanations, correct code, and validate solutions. Whether you're a beginner or an experienced developer looking to refine your skills, this tool is here to assist you.
# System Architecture

The system consists of the following agents:
- **Manager Agent**: Analyzes user requests and delegates tasks to other agents.
- **Teacher Agent**: Provides explanations, examples, and exercises for learning.
- **Coder Agent**: Corrects JavaScript code without explanations.
- **Validator Agent**: Ensures the final output is accurate and error-free.

These agents collaborate to create an interactive and efficient learning experience.

# How to Use
*Python 3.13*

1. Clone the repository

`git clone git@github.com:anasalek/javascript-learning-system.git`

`cd javascript-learning-system`

2. Set up a virtual environment

`python -m venv venv`

`source venv/bin/activate`
Or on Windows:
`venv\Scripts\activate`

3.Install dependencies

`pip install -r requirements.txt`

4. Configure API Key

Create a .env file in the root directory and add your GROQ API key. The file should contain:

`GROQ_API_KEY = gsk_*** #your full API-Token`

You can obtain the API key by signing up at Groq's website

5. Run the Application in the terminal:

`uvicorn app:app --reload --host 127.0.0.1 --port 8000`

Open the link provided in the terminal to access the chat interface.

# Troubleshooting

- **Error: "ModuleNotFoundError"**  
  Ensure all dependencies are installed by running `pip install -r requirements.txt`.

- **Error: "Invalid API Key"**  
  Double-check your `.env` file and ensure the `GROQ_API_KEY` is correct.

- **To invoke the onboarding quiz again**
  
  Open DevTools → Console and run:
  ```
  localStorage.removeItem("js_onboarding_state");
  location.reload();
  ```

- ⚠️ **FULL RESET**

  **WARNING**! this removes **ALL** stored data, including, including: chats, theme, etc.

  Open DevTools → Console and run:
  ```
  localStorage.clear();
  location.reload();
  ```