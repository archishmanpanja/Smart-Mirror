import pyaudio
import speech_recognition as sr

# Initialize recognizer
recognizer = sr.Recognizer()
text='Hello'
# Set up microphone input
with sr.Microphone() as source:
    print("Adjusting for ambient noise... Please wait.")
    recognizer.adjust_for_ambient_noise(source, duration=1)
    print("Listening... Speak now!")

    try:
        # Capture audio from the microphone
        audio = recognizer.listen(source)
        print("Processing your speech...")

        # Convert speech to text using Google Web Speech API
        text = recognizer.recognize_google(audio)
        print("You said:", text)

    except sr.UnknownValueError:
        print("Sorry, I could not understand the audio.")
    except sr.RequestError as e:
        print(f"Could not request results; {e}")

from ollama import chat
import pyttsx3
engine = pyttsx3.init()
stream = chat(
    model='deepseek-r1:1.5b',
    messages=[{'role': 'user', 'content': text}],
    stream=True,
)
for chunk in stream:
  print(chunk['message']['content'], end='', flush=True)
  text=text+' '+chunk['message']['content']
engine.say(text)
#engine.runAndWait()
engine.startLoop(False)
engine.iterate()
engine.endLoop()
