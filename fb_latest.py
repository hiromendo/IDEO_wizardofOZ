#!/usr/bin/env python
# -*- coding: utf-8 -*- 

# Copyright 2017 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Google Cloud Speech API sample application using the streaming API.

NOTE: This module requires the additional dependency `pyaudio`. To install
using pip:

    pip install pyaudio

Example usage:
    python transcribe_streaming_mic.py
"""

# [START import_libraries]
from __future__ import division

import re
import sys
import time

from google.cloud import speech
from google.cloud.speech import enums
from google.cloud.speech import types
import pyaudio
from six.moves import queue

from fbchat import log, Client
from fbchat.models import *
from gtts import gTTS
from os import system
from threading import Timer

import sys
reload(sys)
sys.setdefaultencoding('utf8')
# [END import_libraries]

# Audio recording parameters
RATE = 16000
CHUNK = int(RATE / 10)  # 100ms
RECEIVE_BUFFER_TIME = 0.5
fb_intruction = ['change bot', 'restart', 'worst case', 'problem solving', 'positive thinking']

class MicrophoneStream(object):
    """Opens a recording stream as a generator yielding the audio chunks."""
    def __init__(self, rate, chunk):
        self._rate = rate
        self._chunk = chunk

        # Create a thread-safe buffer of audio data
        self._buff = queue.Queue()
        self.closed = True

    def __enter__(self):
        self._audio_interface = pyaudio.PyAudio()
        self._audio_stream = self._audio_interface.open(
            format=pyaudio.paInt16,
            # The API currently only supports 1-channel (mono) audio
            # https://goo.gl/z757pE
            channels=1, rate=self._rate,
            input=True,input_device_index=2, frames_per_buffer=self._chunk,
            # Run the audio stream asynchronously to fill the buffer object.
            # This is necessary so that the input device's buffer doesn't
            # overflow while the calling thread makes network requests, etc.
            stream_callback=self._fill_buffer,
        )

        self.closed = False

        return self

    def __exit__(self, type, value, traceback):
        self._audio_stream.stop_stream()
        self._audio_stream.close()
        self.closed = True
        # Signal the generator to terminate so that the client's
        # streaming_recognize method will not block the process termination.
        self._buff.put(None)
        self._audio_interface.terminate()

    def _fill_buffer(self, in_data, frame_count, time_info, status_flags):
        """Continuously collect data from the audio stream, into the buffer."""
        self._buff.put(in_data)
        return None, pyaudio.paContinue

    def generator(self):
        while not self.closed:
            # Use a blocking get() to ensure there's at least one chunk of
            # data, and stop iteration if the chunk is None, indicating the
            # end of the audio stream.
            chunk = self._buff.get()
            if chunk is None:
                return
            data = [chunk]

            # Now consume whatever other data's still buffered.
            while True:
                try:
                    chunk = self._buff.get(block=False)
                    if chunk is None:
                        return
                    data.append(chunk)
                except queue.Empty:
                    break

            yield b''.join(data)
# [END audio_stream]


def listen_print_loop(responses):
    """Iterates through server responses and prints them.

    The responses passed is a generator that will block until a response
    is provided by the server.

    Each response may contain multiple results, and each result may contain
    multiple alternatives; for details, see https://goo.gl/tjCPAU.  Here we
    print only the transcription for the top alternative of the top result.

    In this case, responses are provided for interim results as well. If the
    response is an interim one, print a line feed at the end of it, to allow
    the next result to overwrite it, until the response is a final one. For the
    final one, print a newline to preserve the finalized transcription.
    """
    num_chars_printed = 0
    for response in responses:
        if not response.results:
            continue

        # The `results` list is consecutive. For streaming, we only care about
        # the first result being considered, since once it's `is_final`, it
        # moves on to considering the next utterance.
        result = response.results[0]
        if not result.alternatives:
            continue

        # Display the transcription of the top alternative.
        transcript = result.alternatives[0].transcript

        # Display interim results, but with a carriage return at the end of the
        # line, so subsequent lines will overwrite them.
        #
        # If the previous result was longer than this one, we need to print
        # some extra spaces to overwrite the previous result
        overwrite_chars = ' ' * (num_chars_printed - len(transcript))

        if not result.is_final:
            sys.stdout.write(transcript + overwrite_chars + '\r')
            sys.stdout.flush()

            num_chars_printed = len(transcript)

        else:
            transcript_text = transcript + overwrite_chars
            print(transcript_text)
            

            # Exit recognition if any of the transcribed phrases could be
            # one of our keywords.
            #if re.search(r'\b(exit|quit)\b', transcript, re.I):
            num_chars_printed = 0
            print('Exiting..')
            return transcript_text

            


def start_microphone():
    with MicrophoneStream(RATE, CHUNK) as stream:
        audio_generator = stream.generator()
        requests = (types.StreamingRecognizeRequest(audio_content=content)
                    for content in audio_generator)

        responses = client.streaming_recognize(streaming_config, requests)

        # Now, put the transcription responses to use.
        transcript_text = listen_print_loop(responses)
        return transcript_text

class FBClientBot(Client):
    def __init__(self, email, password, **kwargs):
        Client.__init__(self, email, password)
        self.last_timestamp = 0
        self.receive_buffer = []

    def say(self, text):
        tts = gTTS(text=text, lang='en')
        tts.save("test.mp3")
        system("mpg321 test.mp3")
	#system('say -v Victoria'+text)
	#system('espeak "' + text + '"')

    def read_receive_buffer(self, thread_id):
        for msg in self.receive_buffer:
            msg = msg.encode('utf-8').strip()
            self.say(msg)
        while True:
            transcript_text =  start_microphone()
            if transcript_text.lower() == 'alexa':
                thread_id = "100024821950445"
                transcript_text = 'restart'
            elif transcript_text.lower() == 'banana':
                thread_id = "100024128813833"
                transcript_text = 'restart'
            self.send(Message(text=str(transcript_text)), thread_id=thread_id, thread_type=ThreadType.USER)
            if transcript_text.lower() not in fb_intruction:
                break
        self.receive_buffer = []
        self.last_timestamp = 0



    def onMessage(self, author_id, message_object, thread_id, thread_type, **kwargs):
        # import datetime
        # st = datetime.datetime.fromtimestamp(user_response_time).strftime('%Y-%m-%d %H:%M:%S')
        # then you will see timestamp such as "2012-12-15 01:21:05"
        self.markAsDelivered(author_id, thread_id)
        self.markAsRead(author_id)
        log.info("{} from {} in {}".format(message_object, thread_id, thread_type.name))

        if author_id != self.uid:
            msg = message_object.text.lower()
            self.receive_buffer.append(msg)
            if self.last_timestamp == 0:
                Timer(RECEIVE_BUFFER_TIME, self.read_receive_buffer, (thread_id,)).start()
                self.last_timestamp = time.time()
            


if __name__ == '__main__':
    # See http://g.co/cloud/speech/docs/languages
    # for a list of supported languages.
    language_code = 'en-US'  # a BCP-47 language tag

    client = speech.SpeechClient()
    config = types.RecognitionConfig(
        encoding=enums.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=RATE,
        language_code=language_code)
    streaming_config = types.StreamingRecognitionConfig(
        config=config,
        interim_results=True)



    email = "hiromendo@gmail.com" # your facebook account
    password = "nachohiro10" # your facebook password
    fb_client = FBClientBot(email, password)
    fb_target_id = "100024128813833" #"100023051731509" #100024128813833  newrelaxation bot


    while True:
        transcript_text = start_microphone()
        if transcript_text.lower() == 'alexa':
            fb_target_id = "100024821950445"
            transcript_text = 'restart'
        fb_client.send(Message(text=str(transcript_text)), thread_id=fb_target_id, thread_type=ThreadType.USER)
        if transcript_text.lower() not in fb_intruction:
            break
        print('continue')
    fb_client.listen()
