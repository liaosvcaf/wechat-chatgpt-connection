# Origional code https://github.com/marticztn/WeChat-ChatGPT-Automation
# modified by: C. Liao

# Algorithm
#   step 1 get the wechat chat window by its title
#   step 2 taking screenshots
#   step 3 extracting text using an OCR package
#   step 4 sending text to OpenAI's API to obtain an answer
#   step 5 sending the response back to the chat window

import openai
import time
import cv2
import pyautogui as auto
import numpy as np
import pyperclip
from PIL import Image
# from AppKit import NSPasteboard, NSStringPboardType
import clipboard
from colorthief import ColorThief
import json
import pygetwindow as gw
import sys
#import numpy as np
#import tempfile
#import pytesseract # OCR quality is bad for Chinese.
#import easyocr  # OCR quality is bad for mixed Enlighs and Chinese, also very slow on CPU only machine
import logging
from paddleocr import PaddleOCR
from dotenv import load_dotenv
import os

#  User configurable variables, MUST change to your own settings!!
# -------------------
# Replace this with the actual window title of the chat program
# if not certain, run this program once to see all window titles.
# some chat window has strange characters, so use the title prefix instead
chat_window_title_prefix = 'SVCA VIP'
#QUESTION_PREFIX = '@chatgpt'
QUESTION_PREFIX = '机器人'

# the input message box's start position to paste the answer to the chat window's input box
# best download and use the "greenshot" program to find the coordinates of the chat window's input box: 
inx = 1050
iny = 1065
# which OpenAI model to use
# the API key should be stored in the .env file
MODEL = "gpt-3.5-turbo"

# Internal variables 
# -------------------
# shift to hit middle of Copy menu item when sending message to chat window
plusx = 41
plusy = 14

# How long in seconds to wait before checking for new messages again if no new messages are found
SLEEP_TIME = 5    

# TIME limit of the chatbot: 1 hour each time
TIME_LIMT = 3600

# screenshot of the chat window, used for OCR to check if window has changed content.
prev_image_array = np.array([],dtype=float)

# global questions dictionary: avoid answering the same question twice
# using set to be sure that the question is unique
question_dict = set() 


# load the contents of the .env file into os.environ
load_dotenv()

# get the value of the API_KEY environment variable
api_key = os.environ.get('API_KEY')

if api_key is None:
    print("OpenAI's API key not found in environment variables")
    sys.exit(1)

API_KEY = api_key
IMG_NAME = '1.png'
openai.api_key = API_KEY

# msgs is a list of dictionaries.
# the first dictionary is the initial message from the assistant
msgs = [
    {"role": "system", "content": "你是一个很幽默的助手"}
]

# move the mouse cursor to the message box and send message using pasting
# getgreenshot.org software: printscreen to find the coordinates.
def sendMessage(msg: str):    
    auto.moveTo(inx, iny)
    auto.click()
    # auto.hotkey('command', 'v')  # pyautogui
    auto.hotkey('ctrl', 'v')
    auto.press('enter')

# Calling ChatGPT API
# Add answer to the msgs list, with a size limit
def getAnswer(msg: str) -> str:
    # global variable msgs, accessible anywhere in the program
    # msgs is a list of dictionaries!
    global msgs
    print('New message detected: ' + msg)

    # append the user's message info as a dictionary to the msgs list
    msgs.append({"role": "user", "content": msg})
    print(msgs)

    response = openai.ChatCompletion.create(
        model=MODEL,
        messages=msgs,
        # max_tokens = 100,
        temperature=0.8
    )['choices'][0]['message']['content'].strip()
    # strip() removes the leading and trailing spaces

    # append the response info. as a dictionary into the msgs list
    msgs.append({"role": "assistant", "content": response})

    list_as_str = json.dumps(msgs)
    tokens = list_as_str.split()
    token_count = len(tokens)
    # This checks if the length of the msgs list has exceeded 25 elements,
    # and if so, removes the second and third elements of the list.
    # This ensures that the msgs list does not grow too large and consume too much memory.
    if len(msgs) >= 10 or token_count > 2000:
        msgs.pop(1)  # list index id starts from 0
        msgs.pop(2)

    return response

# Capture the new questions from the chat window
# using OCR of the screenshot to extract the text, find the new questions starting with "@chatgpt"
def capture_chat_text(window_title):
    global prev_image_array
    global question_dict
    result =[]      
    windows = gw.getWindowsWithTitle(window_title)
    if len(windows) <= 0:
        print("No window with title '{}' found.".format(window_title))
        sys.exit(1)

    window = windows[0]
    # window = gw.getWindowsWithTitle(window_title)[0]

    if window.visible:
        # Get the window position and size
        x, y, width, height = window.left, window.top, window.width, window.height

        # Capture the window screenshot
        # the returned screenshot variable's type is PIL.Image.Image
        # pyautogui
        screenshot = auto.screenshot(region=(x, y, width, height))

        current_image_array = np.array(screenshot)
        
        if np.array_equal(prev_image_array, current_image_array):
            print("The chat window screenshot is the same as the previous one. No new questions.")            
            return result
        else:
            print("The chat window screenshot is different from the previous one. Detecting new questions...")        
        prev_image_array = current_image_array
        
        # Initialize PaddleOCR with mixed languages (English and Simplified Chinese)
        ocr = PaddleOCR(lang='ch')

        # Perform OCR on the screenshot
        chat_text = ocr.ocr(current_image_array)
        # the output of ocr.ocr() is a list of a single entry, which is a list of tuples
        # very confusing and not intuitive at all!
        for line in chat_text[0]:
                line= line[-1][0]  # last entry of the tuple is the (text, confidence) pair. 
                # check if the line contains a prefix string of "@chatgpt"
                if line.startswith(QUESTION_PREFIX):
                    # get the message after the prefix
                    question = line.split(QUESTION_PREFIX)[1]   
                    # trim the leading and trailing spaces
                    question = question.strip()   
                    if question not in question_dict:
                        question_dict.add(question)
                        print(f"New question: '{question}' has been found. Dict size is {len(question_dict)} now.")
                        # print(question)                                                    
                        # add the new question into a list of results
                        result.append(question)
                    else:
                        print(f"The question: '{question}' has been asked before. Ignoring it.")
                        
        return result                                                      
    else:
        print("Chat window named '{}' not found or not visible.".format(window_title))
        return None

if __name__ == '__main__':
    
    start_time = time.time()    
    if sys.version_info >= (3, 11):
        sys.exit("This script only supports Python versions earlier than 3.11, due to the OCR package used.")
    chat_window_title =''
    # Get all visible windows, print the title of each window
    windows = gw.getAllWindows()
    print('---------------------------------')
    print("All visible windows' titles are:")
    for window in windows:
        if window.visible:    
            print(window.title) 
            if window.title.startswith(chat_window_title_prefix):  
                chat_window_title=window.title
                print(f'Mathed one: chat_window_title={chat_window_title}')
                     
    if chat_window_title == '':
        print(f"No chat window matching prefix {chat_window_title_prefix} was found. Exiting...")
        sys.exit(1)
        
    # Configure logging level for PaddleOCR
    # turn off all warnings
    
    #logging.getLogger("paddleocr").setLevel(logging.ERROR)
    # Set up the logging level
    # logging.basicConfig(level=logging.ERROR)
    # Locate the logger used by PaddleOCR
    paddle_logger = logging.getLogger('ppocr')
    # Set the logging level to ERROR (suppress DEBUG and WARNING messages)
    paddle_logger.setLevel(logging.ERROR)
    
    while True:
        new_questions = capture_chat_text(chat_window_title)
        if new_questions:
            print('---------------------------------')
            for line in new_questions:                
                answer = getAnswer(line)
                print(answer)
                # copy the answer to the clipboard
                pyperclip.copy(answer)
                # paste the answer to the chat window
                sendMessage(answer)            
        else:
            print(f"No new questions extracted from the Chat window titled '{chat_window_title}', waiting for {SLEEP_TIME} seconds before next try...")
            time.sleep(SLEEP_TIME) # must sleep for a while, otherwise the program will run too fast
        elapsed_time = time.time() - start_time
        print(f">>>>>>>  Elapsed time: {elapsed_time:.2f} of total limit of {TIME_LIMT:.2f} seconds")
        # if 
        if elapsed_time > TIME_LIMT:
            print(f">>>>>>>  Elapsed time exceeding limit, exiting...")
            break
         
