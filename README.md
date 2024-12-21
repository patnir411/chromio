Crawler with AI Control

# Overview

This Python script is designed to crawl and interact with Hacker News (https://news.ycombinator.com/) using Chromium for web automation, SQLite for data storage, and OpenAI for natural language processing of user commands. It can operate in two modes:

-   Automatic Mode: Crawls the top 5 articles from Hacker News' front page.
-   Control Mode: Allows users to interact with the browser through natural language commands.

# Features

-   Chromium Automation: Uses PyChromeDevTools for controlling browser actions.
-   Database Storage: Stores crawled page data in SQLite.
-   Natural Language Processing: Utilizes OpenAI API for interpreting user commands.
-   Logging: Detailed logging for debugging and monitoring.

# Installation

1. Ensure Python 3 is installed on your system.
2. Install required libraries:
   pip install PyChromeDevTools sqlite3 openai beautifulsoup4

3. Set up your OpenAI API key as an environment variable:
   export OPENAI_API_KEY="your-api-key-here"

# Usage

-   **Automatic Mode**:
    Run the script without arguments to start crawling:
    python script_name.py

-   **Control Mode**:
    Add `--control` to enable interactive control via natural language:
    python script_name.py --control

You can then enter commands like "go to the next page", "click on the first article", etc.

# Dependencies

-   PyChromeDevTools: For Chromium browser control.
-   SQLite3: For database operations.
-   OpenAI: For natural language command processing.
-   BeautifulSoup: For HTML parsing (though primarily used through JavaScript in this script).
-   JSON, Time, RE, and other standard Python libraries.

# Database Schema

The script creates a table named `pages` with the following structure:
CREATE TABLE IF NOT EXISTS pages (
url TEXT PRIMARY KEY,
title TEXT,
content TEXT,
analysis TEXT,
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

# Security Notes

-   Ensure the script's execution environment is secure; it starts Chromium with remote debugging enabled, which should be restricted to localhost.
-   Use environment variables for API keys and other sensitive data.
-   Be cautious with the OpenAI API usage to avoid unexpected costs or data leakage.
