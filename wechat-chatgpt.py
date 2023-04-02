# Origional code https://github.com/marticztn/WeChat-ChatGPT-Automation
# modified by: C. Liao

# Algorithm
#   step 1 get the wechat chat window by its title
#   step 2 taking screenshots: known limitations: OCR does not work well with multiple line messages
#          to work around this limitation, we enlarge the chat window to be as wide as possible to have single line messages.
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
#chat_window_title_prefix = 'chatgpt聊天'  # <<-------------- chat window title prefix
chat_window_title_prefix = 'chatgpt test'  # <<-------------- chat window title prefix
QUESTION_PREFIX = 'chatgpt'
QUESTION_PREFIX2 = '机器人'

# the input message box's start position to paste the answer to the chat window's input box
# best download and use the "greenshot" program to find the coordinates of the chat window's input box: 
inx = 1252   ## <<-------------- x of input cursor
iny = 954  ## <<-------------- y of input cursor

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

# speed up the processing of individual lines
# skip one if seen before 
line_dict = set()

# load the contents of the .env file into os.environ
load_dotenv()

# get the value of the API_KEY environment variable
# usually saved into the .env file in the same directory as this script
api_key = os.environ.get('API_KEY')

if api_key is None:
    print("OpenAI's API key not found in environment variables")
    sys.exit(1)

API_KEY = api_key
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
    print('Step 3: Get answer for the new question: ' + msg)

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
# merge multiple lines into one question if a line is close to the previous line
def capture_chat_text_for_new_questions(window_title):
    global prev_image_array
    # must use local variable, otherwise the global variable will accumulate lines again?
    merged_chat_text = []  # ordered list, with prefixes kept. keep original order of questions
    global question_dict
    global line_dict
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
        
        # let's try to merge neighboring lines into one line first
        # the first entry of the tuple is the (x1, y1, x2, y2) coordinates of the bounding box
        # we 
        
        # x --->   horizontal axis: column number
        # y is vertical axis: row number

        # (85,193)       (420, 194)
        #   1                2
        #
        #   4                 3
        # (85,207)         (420, 208)      
        # ----------------
        # [84.0, 214.0]    [420.0, 214.0]       // x1 vs. prev x4: almost the same diff<5,   ignore point 3. vs 2
        #   1                  2                // y2 vs. prev y4: different diff<10   
        #
        #   4                  3
        # [84.0, 228.0]  [420.0, 228.0]        
        
        # store the previous line's coordinate of its left bottom corner (point 4)        
        prev_x4 = 0
        prev_y4 = 0
        prev_line = ""  # store the previous line's text, if any
        
        #each line is stored as a list of 2 elements:
        #   0 [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], 
        #   1 [text, confidence] 
        for line in chat_text[0]:
            current_line = line[-1][0]  # last entry of the tuple is the (text, confidence) pair. 
            
            # if processed before, ignore it
            if current_line in line_dict: 
                continue
            # save the current line into the line dictionary           
            line_dict.add(current_line)
            
            # Now a totally new line to process
            x1=line[0][0][0]
            y1=line[0][0][1]            
            # check if x1,y1 is close to the previous line's x4,y4
            # current_line always becomes part of prev_line no matter what
            # a prev_line is always valid
            # we relax x1- prev_x4 to 15 instead of 5, because the text is not aligned
            # due to some leading punctuation mark like . or , etc.
            # the most important distance is the vertical distance, which is y1-prev_y4
            # abs(x1-prev_x4) < 15 and
            if len(prev_line) != 0 and ( abs(y1-prev_y4) < 15 ):
                # merge the current line with the previous line if applicable
                prev_line = prev_line + " " + current_line
            else: 
                # condition 1: no previous line, 
                # 
                # condition 2: the current line is too far away from the previous line
                # we store the prev_line into the merged chart text, and start a new line                   
                                
                # check if first 5 letters are in English, if so, convert to lower case
                #@chatgpt
                if len(line)>5 and line[:5].isalpha():
                    # convert English first 5 letters into all lower case
                    line = line[:5].lower() + line[5:]                
                # a matching prev_line is found, so we store it into the merged_chat_text
                # next time we will skip it early    
                
                # condition 2: the current line is too far away from the previous line
                # we only insert the prev_line if it has a matched prefix string of "@chatgpt"                    
                if len(prev_line) != 0:
                    #print (f"found a new question: {prev_line}")                                     
                    print(f"Step 1: From screenshot, found and add a new merged question with prefix: {prev_line}")
                    merged_chat_text.append(prev_line)                    
                    # mistake: forgot to reset the prev_line to empty string
                    prev_line = ""  # reset the prev_line to empty string
                
                # always making sure pev_line is a valid line if it is the first line of a list of continuous lines
                # a fresh prev_line , only add it if it has a matched prefix string of "@chatgpt"   
                if (current_line.startswith(QUESTION_PREFIX) or current_line.startswith(QUESTION_PREFIX2)):                    
                    prev_line = current_line
                
            prev_x4 = line[0][3][0]
            prev_y4 = line[0][3][1]    

        # store the remaining of prev_line also 
        if len(prev_line) != 0:
            merged_chat_text.append(prev_line)                
            
        # then for merged lines, each will be unique questions with prefixes
        # we just remove the prefix string of "@chatgpt" and store the question into the result list        
        for line in merged_chat_text:
            question = ""
            # remove prefix string of "@chatgpt" if any
            if (line.startswith(QUESTION_PREFIX)):
                question = line.split(QUESTION_PREFIX)[1]
            if (line.startswith(QUESTION_PREFIX2)):
                question = line.split(QUESTION_PREFIX2)[1]
            # trim the leading and trailing spaces
            question = question.strip()       # mistake: line.strip() was used!
            if question not in question_dict:
                question_dict.add(question)
                print(f"Step 2: Stripped prefix for the question: '{question}' has been found. Dict size is {len(question_dict)} now.")
                # print(question)                                                    
                # add the new question into a list of results
                result.append(question)
            else:
                print(f"Step 2: The question: '{question}' has been asked before. Ignoring it.")
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
        new_questions = capture_chat_text_for_new_questions(chat_window_title)
        if new_questions:
            print('---------------------------------')
            for line in new_questions:                
                answer = getAnswer(line)
                print(f"Answer is {answer}")
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
         
