from tkinter import *
import tkinter as tk
import locale
import threading
import queue
import time
import requests
import json
import traceback
import feedparser
from datetime import datetime
from dateutil import tz
import pyaudio
import speech_recognition as sr
from ollama import chat
import pyttsx3
from PIL import Image, ImageTk
from contextlib import contextmanager

# Use a queue to pass messages from the worker thread to the main thread
update_queue = queue.Queue()

# Initialize recognizer and pyttsx3 engine
recognizer = sr.Recognizer()
engine = pyttsx3.init()

LOCALE_LOCK = threading.Lock()

ui_locale = '' # e.g. 'fr_FR' fro French, '' as default
time_format = 12 # 12 or 24
date_format = "%b %d, %Y" # check python doc for strftime() for options
news_country_code = 'IN'
weather_api_token = '<TOKEN>' # create account at https://darksky.net/dev/
weather_lang = 'en' # see https://darksky.net/dev/docs/forecast for full list of language parameters values
weather_unit = 'us' # see https://darksky.net/dev/docs/forecast for full list of unit parameters values
latitude = None # Set this if IP location lookup does not work for you (must be a string)
longitude = None # Set this if IP location lookup does not work for you (must be a string)
xlarge_text_size = 94
large_text_size = 48
medium_text_size = 20
small_text_size = 13
ipregistry_key='jvlysguuxxoajrw9'

@contextmanager
def setlocale(name): #thread proof function to work with locale
    with LOCALE_LOCK:
        saved = locale.setlocale(locale.LC_ALL)
        try:
            yield locale.setlocale(locale.LC_ALL, name)
        finally:
            locale.setlocale(locale.LC_ALL, saved)

# maps open weather icons to
# icon reading is not impacted by the 'lang' parameter
icon_lookup = {
    'clear-day': "assets/Sun.png",  # clear sky day
    'wind': "assets/Wind.png",   #wind
    'cloudy': "assets/Cloud.png",  # cloudy day
    'partly-cloudy-day': "assets/PartlySunny.png",  # partly cloudy day
    'rain': "assets/Rain.png",  # rain day
    'snow': "assets/Snow.png",  # snow day
    'snow-thin': "assets/Snow.png",  # sleet day
    'fog': "assets/Haze.png",  # fog day
    'clear-night': "assets/Moon.png",  # clear sky night
    'partly-cloudy-night': "assets/PartlyMoon.png",  # scattered clouds night
    'thunderstorm': "assets/Storm.png",  # thunderstorm
    'tornado': "assests/Tornado.png",    # tornado
    'hail': "assests/Hail.png"  # hail
}

# --- Patch for AttributeError: '_last_child_ids' ---
if not hasattr(tk.Tk, '_last_child_ids'):
    def _winfo_children(self):
        result = self.tk.splitlist(self.tk.call('winfo', 'children', self._w))
        return [self.nametowidget(x) for x in result]
    tk.Tk.winfo_children = _winfo_children
# --- End of patch ---

def run_speech_and_llm():
    """
    Function to run continuously in a separate thread.
    It handles speech recognition, LLM interaction, and text-to-speech.
    """
    while True:
        try:
            # Step 1: Capture audio from the microphone
            update_queue.put("Listening... Speak now!\n")
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=1)
                audio = recognizer.listen(source, timeout=5)

            # Step 2: Convert speech to text
            update_queue.put("Processing your speech...\n")
            recognized_text = recognizer.recognize_google(audio)
            update_queue.put(f"You said: {recognized_text}\n")

            # Step 3: Interact with Ollama
            full_response_text = ""
            update_queue.put("LLM Response: ")
            stream = chat(
                model='deepseek-r1:1.5b',
                messages=[{'role': 'user', 'content': recognized_text}],
                stream=True,
            )
            for chunk in stream:
                content = chunk['message']['content']
                full_response_text += content
                # Send chunks to the main thread for real-time display
                update_queue.put(content)
            update_queue.put("\n")

            # Step 4: Perform Text-to-Speech (TTS)
            engine.say(full_response_text)
            engine.runAndWait()

        except sr.WaitTimeoutError:
            continue
        except sr.UnknownValueError:
            update_queue.put("Sorry, I could not understand the audio.\n")
        except sr.RequestError as e:
            update_queue.put(f"Could not request results; {e}\n")
        except Exception as e:
            update_queue.put(f"An error occurred: {e}\n")
        
        time.sleep(1)

def check_queue(text_widget):
    """
    Checks the queue for new messages from the worker thread and updates the GUI.
    This function runs in the main Tkinter thread.
    """
    try:
        while True:
            message = update_queue.get_nowait()
            text_widget.config(state=tk.NORMAL)
            text_widget.insert(tk.END, message)
            text_widget.see(tk.END)
            text_widget.config(state=tk.DISABLED)
            update_queue.task_done()
    except queue.Empty:
        pass
    
    text_widget.after(1000, check_queue, text_widget)

class SpeechRecognitionDisplay(Frame):
    def __init__(self, parent, *args, **kwargs):
        Frame.__init__(self, parent, bg='black')
        
        self.text_area = tk.Text(self, wrap="word", width=80, height=10, state=tk.DISABLED,
                                 bg="black", fg="white", font=('Helvetica', small_text_size))
        self.text_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        # Start the queue checker
        self.text_area.after(100, check_queue, self.text_area)

class Clock(Frame):
    def __init__(self, parent, *args, **kwargs):
        Frame.__init__(self, parent, bg='black')
        # initialize time label
        self.time1 = ''
        self.timeLbl = Label(self, font=('Helvetica', large_text_size), fg="white", bg="black")
        self.timeLbl.pack(side=TOP, anchor=E)
        # initialize day of week
        self.day_of_week1 = ''
        self.dayOWLbl = Label(self, text=self.day_of_week1, font=('Helvetica', medium_text_size), fg="white", bg="black")
        self.dayOWLbl.pack(side=TOP, anchor=E)
        # initialize date label
        self.date1 = ''
        self.dateLbl = Label(self, text=self.date1, font=('Helvetica', medium_text_size), fg="white", bg="black")
        self.dateLbl.pack(side=TOP, anchor=E)
        self.tick()

    def tick(self):
        with setlocale(ui_locale):
            if time_format == 12:
                time2 = time.strftime('%I:%M %p') #hour in 12h format
            else:
                time2 = time.strftime('%H:%M') #hour in 24h format

            day_of_week2 = time.strftime('%A')
            date2 = time.strftime(date_format)
            # if time string has changed, update it
            if time2 != self.time1:
                self.time1 = time2
                self.timeLbl.config(text=time2)
            if day_of_week2 != self.day_of_week1:
                self.day_of_week1 = day_of_week2
                self.dayOWLbl.config(text=day_of_week2)
            if date2 != self.date1:
                self.date1 = date2
                self.dateLbl.config(text=date2)
            # calls itself every 200 milliseconds
            self.timeLbl.after(200, self.tick)

class Weather(Frame):
    def __init__(self, parent, *args, **kwargs):
        Frame.__init__(self, parent, bg='black')
        self.temperature = ''
        self.forecast = ''
        self.location = ''
        self.currently = ''
        self.icon = ''
        self.temp=''
        self.wind_speed=''
        self.description=''
        self.sunrise=''
        self.sunset=''
        self.Latest_Confirmed=''
        self.Latest_Recovered=''
        self.Latest_Deaths=''
        self.degreeFrm = Frame(self, bg="black")
        self.degreeFrm.pack(side=TOP, anchor=W)
        self.temperatureLbl = Label(self.degreeFrm, font=('Helvetica', xlarge_text_size), fg="white", bg="black")
        self.temperatureLbl.pack(side=LEFT, anchor=N)
        self.iconLbl = Label(self.degreeFrm, bg="black")
        self.iconLbl.pack(side=LEFT, anchor=N, padx=20)
        self.currentlyLbl = Label(self, font=('Helvetica', medium_text_size), fg="white", bg="black")
        self.currentlyLbl.pack(side=TOP, anchor=W)
        self.tempLbl = Label(self, font=('Helvetica', medium_text_size), fg="white", bg="black")
        self.tempLbl.pack(side=TOP, anchor=W)
        self.wind_speedLbl = Label(self, font=('Helvetica', medium_text_size), fg="white", bg="black")
        self.wind_speedLbl.pack(side=TOP, anchor=W)
        self.descriptionLbl = Label(self, font=('Helvetica', medium_text_size), fg="white", bg="black")
        self.descriptionLbl.pack(side=TOP, anchor=W)  
        self.sunriseLbl = Label(self, font=('Helvetica', medium_text_size), fg="white", bg="black")
        self.sunriseLbl.pack(side=TOP, anchor=W)
        self.sunsetLbl = Label(self, font=('Helvetica', medium_text_size), fg="white", bg="black")
        self.sunsetLbl.pack(side=TOP, anchor=W)
        self.locationLbl = Label(self, font=('Helvetica', medium_text_size), fg="white", bg="black")
        self.locationLbl.pack(side=TOP, anchor=W)
# The rest of your existing classes (News, Calendar, etc.) would go here.
# For simplicity, we only include the relevant parts from the provided code.
        self.get_weather()

    def get_ip(self):
        try:
            ip_url = "http://jsonip.com/"
            req = requests.get(ip_url)
            ip_json = json.loads(req.text)
            return ip_json['ip']
        except Exception as e:
            traceback.print_exc()
            return "Error: %s. Cannot get ip." % e
        
    def get_weather(self):
        try:

            if latitude is None and longitude is None:
                # get location
                ip_url = "http://ipv4.jsonip.com/"
                req = requests.get(ip_url)
                ip_json = json.loads(req.text)['ip']

                location_req_url = f'https://api.ipregistry.co/{ip_json}?key={ipregistry_key}'
                r = requests.get(location_req_url)

                location_obj = json.loads(r.text)
                lat = location_obj['location']['latitude']
                long = location_obj['location']['longitude']
                city_info=location_obj['location']['city']
                region=location_obj['location']['region']['code']
                location2 = "%s, %s" % (location_obj['location']['city'], location_obj['location']['region']['code'])

                weather_url='http://api.openweathermap.org/data/2.5/weather?q={}&appid=abbe7a4f83dc934bffc619d5957bdcb0'.format(city_info)


            res=requests.get(weather_url)
            data=res.json()
            temp2=round(convert_kelvin_to_Celsius(data['main']['temp']),1)
            wind_speed2=data['wind']['speed']
            description2=data['weather'][0]['description']
            temp3='Temperature: {}°C'.format(temp2)
            wind_speed3='Wind Speed: {} m/s'.format(wind_speed2)
            description3='Description: {}'.format(description2)
            sunrise2=data['sys']['sunrise']
            sunset2=data['sys']['sunset']
            utc_sunrise2 = datetime.fromtimestamp(sunrise2) 
            
            utc_sunset2 = datetime.fromtimestamp(sunset2)
           
            utc_sunrise3=utc_sunrise2.strftime("%H:%M:%S")
            utc_sunset3=utc_sunset2.strftime("%H:%M:%S")
            utc_sunrise4='Sunrise: {}'.format(utc_sunrise3)
            utc_sunset4='Sunset: {}'.format(utc_sunset3)
            data1=requests.get('https://api.covid19india.org/states_daily.json')

            
            if self.sunrise != utc_sunrise2:
                self.sunrise = utc_sunrise2
                self.sunriseLbl.config(text=utc_sunrise4)
                
            if self.sunset != utc_sunset2:
                self.sunset = utc_sunset2
                self.sunsetLbl.config(text=utc_sunset4)
            
            if self.temp != temp2:
                self.temp = temp2
                self.tempLbl.config(text=temp3)
                
            if self.wind_speed != wind_speed2:
                self.wind_speed = wind_speed2
                self.wind_speedLbl.config(text=wind_speed3)
            
            if self.description != description2:
                self.description = description2
                self.descriptionLbl.config(text=description3)
                
                
            if self.location != location2:
                if location2 == ", ":
                    self.location = "Cannot Pinpoint Location"
                    self.locationLbl.config(text="Cannot Pinpoint Location")
                else:
                    self.location = location2
                    self.locationLbl.config(text=location2)
            if self.description != description2:
                self.description = description2
                self.descriptionLbl.config(text=description3)
                 
               # print('Temperature: {}°C'.format(temp))
                #print('Wind Speed: {} m/s'.format(wind_speed))
                #print('Description: {}'.format(description)) 
                
        except Exception as e:
            traceback.print_exc()
            print ("Error: %s. Cannot get weather." % e)

        self.after(10000, self.get_weather)       
 
@staticmethod
def convert_kelvin_to_fahrenheit(kelvin_temp):
        return 1.8 * (kelvin_temp - 273) + 32
def convert_kelvin_to_Celsius(kelvin_temp):
        return (kelvin_temp - 273)

class News(Frame):
    def __init__(self, parent, *args, **kwargs):
        Frame.__init__(self, parent, *args, **kwargs)
        self.config(bg='black')
        self.title = 'News' # 'News' is more internationally generic
        self.newsLbl = Label(self, text=self.title, font=('Helvetica', medium_text_size), fg="white", bg="black")
        self.newsLbl.pack(side=TOP, anchor=W)
        self.headlinesContainer = Frame(self, bg="black")
        self.headlinesContainer.pack(side=TOP)
        self.get_headlines()

    def get_headlines(self):
        try:
            # remove all children
            for widget in self.headlinesContainer.winfo_children():
                widget.destroy()
            if news_country_code == None:
                headlines_url = "https://news.google.com/news?ned=us&output=rss"
            else:
                headlines_url = "https://news.google.com/news?ned=%s&output=rss" % news_country_code

            feed = feedparser.parse(headlines_url)

            for post in feed.entries[0:9]:
                headline = NewsHeadline(self.headlinesContainer, post.title)
                headline.pack(side=TOP, anchor=W)
                
        except Exception as e:
            traceback.print_exc()
            print ("Error: %s. Cannot get news." % e)

        self.after(10000, self.get_headlines)


class NewsHeadline(Frame):
    def __init__(self, parent, event_name=""):
        Frame.__init__(self, parent, bg='black')

        image = Image.open("assets/Newspaper.png")
        image = image.resize((25, 25), Image.LANCZOS)
        image = image.convert('RGB')
        photo = ImageTk.PhotoImage(image)

        self.iconLbl = Label(self, bg='black', image=photo)
        self.iconLbl.image = photo
        self.iconLbl.pack(side=LEFT, anchor=N)

        self.eventName = event_name
        self.eventNameLbl = Label(self, text=self.eventName, font=('Helvetica', small_text_size), fg="white", bg="black")
        self.eventNameLbl.pack(side=LEFT, anchor=N)


class Calendar(Frame):
    def __init__(self, parent, *args, **kwargs):
        Frame.__init__(self, parent, bg='black')
        self.title = 'Ask me'
        self.calendarLbl = Label(self, text=self.title, font=('Helvetica', medium_text_size), fg="white", bg="black")
        self.calendarLbl.pack(side=TOP, anchor=E)
        self.calendarEventContainer = Frame(self, bg='black')
        self.calendarEventContainer.pack(side=TOP, anchor=E)
        self.get_events()

    def get_events(self):
        #TODO: implement this method
        # reference https://developers.google.com/google-apps/calendar/quickstart/python

        # remove all children
        for widget in self.calendarEventContainer.winfo_children():
            widget.destroy()

        calendar_event = CalendarEvent(self.calendarEventContainer)
        calendar_event.pack(side=TOP, anchor=E)
        pass


class CalendarEvent(Frame):
    def __init__(self, parent, event_name="Event 1"):
        Frame.__init__(self, parent, bg='black')
        self.eventName = event_name
        self.eventNameLbl = Label(self, text=self.eventName, font=('Helvetica', small_text_size), fg="white", bg="black")
        self.eventNameLbl.pack(side=TOP, anchor=E)



class FullscreenWindow:
    def __init__(self):
        self.tk = Tk()
        self.tk.configure(background='black')
        self.tk.bind('<Escape>', self.toggle_fullscreen)
        self.tk.bind('<F11>', self.toggle_fullscreen)
        self.frame = Frame(self.tk, background='black')
        self.frame.pack(fill='both', expand=True)
        self.topFrame = Frame(self.tk, background = 'black')
        self.bottomFrame = Frame(self.tk, background = 'black')
        self.topFrame.pack(side = TOP, fill=BOTH, expand = YES)
        self.bottomFrame.pack(side = BOTTOM, fill=BOTH, expand = YES)

        self.state = False
        self.tk.bind("<Return>", self.toggle_fullscreen)
        self.tk.bind("<Escape>", self.end_fullscreen)

        # Voice Assistant display
        self.speech_display = SpeechRecognitionDisplay(self.frame)
        self.speech_display.pack(side=TOP, fill=X)

        # Clock display
        self.clock = Clock(self.frame)
        self.clock.pack(side=RIGHT, anchor=N, padx=20, pady=60)

        # weather
        self.weather = Weather(self.topFrame)
        self.weather.pack(side=LEFT, anchor=N, padx=100, pady=30)
        # news
        self.news = News(self.topFrame)
        self.news.pack(side=RIGHT, anchor=S, padx=100, pady=90)
        
        # Start the continuous voice recognition in a daemon thread
        threading.Thread(target=run_speech_and_llm, daemon=True).start()

    def toggle_fullscreen(self, event=None):
        self.state = not self.state # Just toggling the boolean
        self.tk.attributes("-fullscreen", self.state)
        return "break"
    def end_fullscreen(self, event=None):
        self.state = False
        self.tk.attributes("-fullscreen", False)
        return "break"

    def run(self):
        self.tk.mainloop()

if __name__ == '__main__':
    w = FullscreenWindow()
    w.run()
