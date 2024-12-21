#!/usr/bin/env python3

import PyChromeDevTools
import sqlite3
import time
import re
from urllib.parse import urljoin, urlparse
from openai import OpenAI
from typing import List, Set, Dict, Any, Union
from dataclasses import dataclass
import json
import logging
import sys
import subprocess
import socket
import time
from bs4 import BeautifulSoup

def is_port_open(host: str, port: int) -> bool:
    """Check if a port is open on the given host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        try:
            sock.connect((host, port))
            return True
        except (socket.timeout, ConnectionRefusedError):
            return False

def start_chromium():
    """Start Chromium and wait until it's ready."""
    chromium_process = subprocess.Popen([
        "chromium", 
        "--remote-debugging-port=9222", 
        "--remote-allow-origins=http://localhost:9222"
    ])
    
    while not is_port_open("localhost", 9222):
        print("Waiting for Chromium to start...")
        time.sleep(1)
    
    print("Chromium started and ready.")
    return chromium_process

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('crawler.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class PageData:
    url: str
    title: str
    content: str
    analysis: str

class ChromeTools:
    def __init__(self, chrome: PyChromeDevTools.ChromeInterface):
        self.chrome = chrome
        self.logger = logging.getLogger(__name__ + '.ChromeTools')

    def navigate_to_url(self, url: str) -> Dict[str, Any]:
        self.logger.info(f"Navigating to URL: {url}")
        try:
            self.chrome.Page.navigate(url=url)
            self.chrome.wait_event("Page.loadEventFired", timeout=10)
            self.logger.debug(f"Successfully navigated to {url}")
            return {"status": "success", "url": url}
        except Exception as e:
            self.logger.error(f"Failed to navigate to {url}: {str(e)}")
            raise

    def get_page_content(self) -> Dict[str, str]:
        """Get the full HTML content of the current page"""
        self.logger.debug("Getting page content")
        try:
            dom_response = self.chrome.DOM.getDocument()
            if not dom_response:
                raise Exception("Failed to get DOM document")
            self.logger.debug(f"DOM response: {str(dom_response)[:200]}...")

            root_node_id = dom_response[0]["result"]["root"]["nodeId"]
            self.logger.debug(f"Root node ID: {str(root_node_id)[:200]}...")

            html_response = self.chrome.DOM.getOuterHTML(nodeId=root_node_id)
            self.logger.debug(f"HTML response: {str(html_response)[:200]}...")

            # Extract the 'outerHTML' string from the response
            content = html_response[0]["result"]["outerHTML"]
            self.logger.debug(f"Successfully retrieved page content: {str(content)[:200]}...")
            return {"content": content}
        except Exception as e:
            self.logger.error(f"Failed to get page content: {str(e)}")
            raise

    def get_page_title(self) -> Dict[str, str]:
        self.logger.debug("Getting page title")
        try:
            result = self.chrome.Runtime.evaluate(expression='document.title')
            self.logger.debug(f"Retrieved page title: {result['result']['value']}")
            return {"title": result["result"]["value"]}
        except Exception as e:
            self.logger.error(f"Failed to get page title: {str(e)}")
            raise

    def click_element(self, selector: str) -> Dict[str, Any]:
        self.logger.info(f"Clicking element with selector: {selector}")
        try:
            script = f'document.querySelector("{selector}").click()'
            self.chrome.Runtime.evaluate(expression=script)
            self.logger.debug(f"Successfully clicked element: {selector}")
            return {"status": "success", "clicked": selector}
        except Exception as e:
            self.logger.error(f"Failed to click element {selector}: {str(e)}")
            raise

    def scroll_page(self, amount: int) -> Dict[str, Any]:
        self.logger.debug(f"Scrolling page by {amount} pixels")
        try:
            script = f'window.scrollBy(0, {amount})'
            self.chrome.Runtime.evaluate(expression=script)
            self.logger.debug(f"Successfully scrolled page by {amount} pixels")
            return {"status": "success", "scrolled": amount}
        except Exception as e:
            self.logger.error(f"Failed to scroll page: {str(e)}")
            raise

    def go_back(self) -> Dict[str, Any]:
        self.logger.debug("Going back one page")
        try:
            self.chrome.Page.goBack()
            self.chrome.wait_event("Page.loadEventFired", timeout=10)
            return {"status": "success", "action": "back"}
        except Exception as e:
            self.logger.error(f"Failed to go back: {str(e)}")
            raise

    def go_forward(self) -> Dict[str, Any]:
        self.logger.debug("Going forward one page")
        try:
            self.chrome.Page.goForward()
            self.chrome.wait_event("Page.loadEventFired", timeout=10)
            return {"status": "success", "action": "forward"}
        except Exception as e:
            self.logger.error(f"Failed to go forward: {str(e)}")
            raise

    def analyze_html_with_js(self) -> Dict[str, Any]:
        self.logger.info("Analyzing HTML content with JavaScript")
        try:
            script = """
            const links = Array.from(document.querySelectorAll('a')).map(a => a.href);
            return links;
            """
            result = self.chrome.Runtime.evaluate(expression=script)
            links = result["result"]["value"]
            self.logger.info(f"Found {len(links)} links in the HTML content")
            return {"status": "success", "links": links}
        except Exception as e:
            self.logger.error(f"Failed to analyze HTML content: {str(e)}")
            return {"status": "error", "message": str(e)}

class Crawler:
    def __init__(self, db_path: str = "crawler.db", control_mode: bool = False):
        self.logger = logging.getLogger(__name__ + '.Crawler')
        self.logger.info("Initializing Crawler")
        self.db_path = db_path
        self.chrome = PyChromeDevTools.ChromeInterface()
        self.chrome_tools = ChromeTools(self.chrome)
        self.client = OpenAI()
        self.visited: Set[str] = set()
        self.control_mode = control_mode
        self.message_history = []
        self.setup_database()
        self.setup_chrome()
        self.logger.info("Crawler initialized successfully")

    def setup_database(self):
        self.logger.info(f"Setting up database at {self.db_path}")
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS pages (
                        url TEXT PRIMARY KEY,
                        title TEXT,
                        content TEXT,
                        analysis TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            self.logger.info("Database setup completed")
        except Exception as e:
            self.logger.error(f"Database setup failed: {str(e)}")
            raise

    def setup_chrome(self):
        self.logger.info("Setting up Chrome")
        try:
            self.chrome.Network.enable()
            self.chrome.Page.enable()
            self.chrome.DOM.enable()
            self.logger.info("Chrome setup completed")
        except Exception as e:
            self.logger.error(f"Chrome setup failed: {str(e)}")
            raise

    def map_hn_content(self, page_content_str: str) -> Dict[str, Any]:
        """
        Analyze Hacker News HTML content to extract navigable elements and links.
        Returns a structured mapping of clickable items (stories, nav items, etc.).
        """
        self.logger.info("Starting to map HN content")
        self.logger.debug(f"Content length: {len(page_content_str)} characters")

        system_prompt = (
            "You are an AI assistant that analyzes HTML content. "
            "Extract interactable-specific elements and output a structured JSON array. "
            "For each element, provide:\n"
            "- text\n"
            "- type: story|comment|nav|vote|profile\n"
            "- url\n"
            "- selector\n"
            "Preserve the order they appear in the HTML."
            "*** CRITICALLY IMPORTANT: ONLY GET THE TOP 10 ITEMS, BECAUSE THE USER HAS LIMITED ATTENTION SPAN ***"
        )

        messages = [
            {
                "role": "system", 
                "content": system_prompt
            },
            {
                "role": "user",
                "content": f"HTML Content:\n\n{page_content_str}"
            }
        ]

        try:
            self.logger.debug("Sending request to OpenAI API")
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages
            )
            self.logger.debug("Successfully received response from OpenAI")
            # Attempt to parse JSON
            content = response.choices[0].message.content
            self.logger.info(f"Successfully mapped HN content: {content[:1000]}...")
            return content

        except Exception as e:
            self.logger.error(f"Failed to map HN content: {str(e)}")
            return {"status": "error", "message": str(e)}

    def process_gpt_command(self, user_query: str) -> Dict[str, Any]:
        """Process a natural language user query via GPT to control the browser."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "navigate_to_url",
                    "description": "Navigate the browser to a specific URL",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "The URL to navigate to"
                            }
                        },
                        "required": ["url"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "click_element",
                    "description": "Click an element on the page using CSS selector",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "selector": {
                                "type": "string",
                                "description": "CSS selector for the element to click"
                            }
                        },
                        "required": ["selector"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "scroll_page",
                    "description": "Scroll the page by a specified number of pixels",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "amount": {
                                "type": "integer",
                                "description": "Number of pixels to scroll (positive for down, negative for up)"
                            }
                        },
                        "required": ["amount"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_page_content",
                    "description": "Get the full HTML content of the current page",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_page_title",
                    "description": "Get the title of the current page",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "go_back",
                    "description": "Go back one page in browser history",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "go_forward", 
                    "description": "Go forward one page in browser history",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            }
        ]

        try:
            # Record user query
            self.message_history.append({"role": "user", "content": user_query})

            # Chat completion request
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a browser automation assistant. Interpret commands "
                            "and translate them into appropriate browser actions using "
                            "the available tools."
                        )
                    },
                    *self.message_history
                ],
                tools=tools,
                tool_choice="auto"
            )

            # The assistant's top-level message
            assistant_msg = response.choices[0].message if response.choices else None

            # Retrieve any function calls
            tool_calls = []
            if assistant_msg and assistant_msg.tool_calls:
                tool_calls = assistant_msg.tool_calls

            # Build a message object to store
            message_obj = {"role": "assistant", "content": assistant_msg.content if assistant_msg else None}
            if tool_calls:
                # Each tool call must have "id" and "type" per the new function-calling spec
                message_obj["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in tool_calls
                ]
            self.message_history.append(message_obj)

            for tool_call in tool_calls:
                t_id = tool_call.id
                name = tool_call.function.name
                arg_str = tool_call.function.arguments
                args = json.loads(arg_str) if arg_str else {}

                # Execute the appropriate tool and get status
                status = None
                if name == "navigate_to_url":
                    status = self.chrome_tools.navigate_to_url(args["url"])
                    mapped_content = self.map_hn_content(self.get_page_content()["content"])
                    status["mapped_content"] = mapped_content
                elif name == "click_element":
                    status = self.chrome_tools.click_element(args["selector"])
                elif name == "scroll_page":
                    status = self.chrome_tools.scroll_page(args["amount"])
                elif name == "get_page_content":
                    status = self.chrome_tools.get_page_content()
                elif name == "get_page_title":
                    status = self.chrome_tools.get_page_title()
                elif name == "go_back":
                    status = self.chrome_tools.go_back()
                elif name == "go_forward":
                    status = self.chrome_tools.go_forward()

                # Append tool response for each tool call
                self.message_history.append({
                    "role": "tool",
                    "name": name,
                    "content": json.dumps(status),
                    "tool_call_id": t_id
                })

            return {"status": "success", "message": assistant_msg.content if assistant_msg else "No response."}

        except Exception as e:
            self.logger.error(f"Error processing GPT command: {str(e)}")
            return {"status": "error", "message": str(e)}

    def get_article_links(self) -> List[str]:
        self.logger.info("Getting article links")
        try:
            script = """
            const links = Array.from(document.querySelectorAll('.titleline > a')).slice(0, 5);
            return links.map(link => link.href);
            """
            result = self.chrome.Runtime.evaluate(expression=script)
            links = result[0]["result"]["value"]
            self.logger.info(f"Found {len(links)} article links")
            return links
        except Exception as e:
            self.logger.error(f"Failed to get article links: {str(e)}")
            return []

    def get_page_content(self) -> str:
        self.logger.debug("Getting page content")
        return self.chrome_tools.get_page_content()

    def get_page_title(self) -> str:
        self.logger.debug("Getting page title")
        return self.chrome_tools.get_page_title()["title"]

    def store_page(self, page_data: PageData):
        self.logger.info(f"Storing page data for URL: {page_data.url}")
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO pages (url, title, content, analysis)
                    VALUES (?, ?, ?, ?)
                    """,
                    (page_data.url, page_data.title, page_data.content, page_data.analysis)
                )
            self.logger.debug("Page data stored successfully")
        except Exception as e:
            self.logger.error(f"Error storing page data: {str(e)}")
            raise

    def crawl_page(self, url: str):
        if url in self.visited:
            self.logger.info(f"Skipping already visited URL: {url}")
            return

        self.visited.add(url)
        self.logger.info(f"Crawling: {url}")
        try:
            self.chrome_tools.navigate_to_url(url)
            time.sleep(2)
            content = self.get_page_content()
            title = self.get_page_title()
            analysis_result = self.chrome_tools.analyze_html_with_js()

            page_data = PageData(
                url=url,
                title=title,
                content=str(content),
                analysis=json.dumps(analysis_result)
            )
            self.store_page(page_data)

            self.logger.info(f"Crawl completed for {url}")
        except Exception as e:
            self.logger.error(f"Error crawling {url}: {str(e)}")

def main():
    chromium_process = start_chromium()
    logger.info("Starting crawler application")
    control_mode = "--control" in sys.argv
    crawler = Crawler(control_mode=control_mode)

    if control_mode:
        logger.info("Starting in control mode - use natural language to control the browser")
        while True:
            try:
                user_query = input("Enter your command (or 'exit' to quit): ")
                if user_query.lower() == "exit":
                    break
                result = crawler.process_gpt_command(user_query)
                print("Result:", result)
                time.sleep(1)
            except KeyboardInterrupt:
                break
    else:
        start_url = "https://news.ycombinator.com/"
        crawler.chrome_tools.navigate_to_url(start_url)
        time.sleep(2)
        article_links = crawler.get_article_links()
        for link in article_links:
            crawler.crawl_page(link)
            time.sleep(1)

    crawler.chrome.Browser.close()
    chromium_process.terminate()
    logger.info("Application completed successfully")

if __name__ == "__main__":
    main()