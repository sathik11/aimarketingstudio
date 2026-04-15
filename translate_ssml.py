import os  
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape
import re
from openai import OpenAI
import azure.cognitiveservices.speech as speechsdk
from azure.storage.blob import BlobServiceClient
import uuid
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv


def normalize_openai_base_url(raw_endpoint):
    endpoint = (raw_endpoint or "").rstrip("/")
    if not endpoint:
        return "https://your-openai-resource.openai.azure.com/openai/v1/"
    if endpoint.endswith("/openai/v1") or endpoint.endswith("/openai/v1/"):
        return f"{endpoint.rstrip('/')}/"
    if ".openai.azure.com" in endpoint and "/openai/" not in endpoint:
        return f"{endpoint}/openai/v1/"
    return f"{endpoint}/"


load_dotenv()
AUDIO_OUTPUT_DIR = os.path.abspath(os.getenv("LOCAL_AUDIO_OUTPUT_DIR", "generated_audio"))
os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)

endpoint = normalize_openai_base_url(
    os.getenv("AZURE_OPENAI_ENDPOINT", os.getenv("ENDPOINT_URL", "https://your-openai-resource.openai.azure.com"))
)
deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", os.getenv("DEPLOYMENT_NAME", "gpt-5.4"))
credential = DefaultAzureCredential()
ai_token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")

client = OpenAI(
    base_url=endpoint,
    api_key=ai_token_provider,
)

SYSTEM_PROMPT = """
## Who you are 
    You are an AI Taglish Translator who is expert in translating pure english to filipino context. You work for a Bank named "BDO".
     
 
## what you must do \nTranslate incoming text into taglish ie. causual filipino text. 
                Return only the translated taglish text.
                ** You are receiving text only for translation so DO NOT add any additional sentences or XML/SSML markup. 
    - Tonality must be casual and professional and must reflect bank customer service scenarios.
  - Always express numbers in english words. if its telephone number return it as every number as english word
    e.g (02) 6321 8000 must be translated as (zero two) six three two one eight zero zero zero.

#  What you carefully consider
   - Text should never have be in tagalog alone . Numbers should always be in english and expressed in words. 
   - Whenever your user provided text has uppercase BDO - keep it as BDO (pronunciation is handled separately)
   - Translation must always be taglish. You can change the order of sentence to make it grammatically /colloquially correct for taglish, but dont add any additional context or change the meaning of the sentence.
    - Provide only the final translated text.
   
#### Guidance on Azure SSML as per their documentation - This is for your reference: 
    ```\nSome examples of contents that are allowed in each element are described in the following list:
        audio: The body of the audio element can contain plain text or SSML markup that's spoken if the audio file is unavailable or unplayable. The audio element can also contain text and the following elements: audio, break, p, s, phoneme, prosody, say-as, and sub.
        bookmark: This element can't contain text or any other elements.\nbreak: This element can't contain text or any other elements.
        emphasis: This element can contain text and the following elements: audio, break, emphasis, lang, phoneme, prosody, say-as, and sub.
        lang: This element can contain all other elements except mstts:backgroundaudio, voice, and speak.
        mstts:embedding: This element can contain text and the following elements: audio, break, emphasis, lang, phoneme, prosody, say-as, and sub.
        mstts:express-as: This element can contain text and the following elements: audio, break, emphasis, lang, phoneme, prosody, say-as, and sub.
        mstts:silence: This element can't contain text or any other elements.\nmstts:viseme: This element can't contain text or any other elements.
        p: This element can contain text and the following elements: audio, break, phoneme, prosody, say-as, sub, mstts:express-as, and s.
        phoneme: This element can only contain text and no other elements.
        prosody: This element can contain text and the following elements: audio, break, p, phoneme, prosody, say-as, sub, and s.
        s: This element can contain text and the following elements: audio, break, phoneme, prosody, say-as, mstts:express-as, and sub.
        say-as: This element can only contain text and no other elements.\nsub: This element can only contain text and no other elements.
        speak: The root element of an SSML document. This element can contain the following elements: mstts:backgroundaudio and voice.
        voice: This element can contain all other elements except mstts:backgroundaudio and speak.
        strength: The relative duration of a pause by using one of the following values:\nx-weak, weak, medium (default), strong, x-strong
        time: \tThe absolute duration of a pause in seconds (such as 2s) or milliseconds (such as 500ms). Valid values range from 0 to 20000 milliseconds. If you set a value greater than the supported maximum, the service uses 20000ms. If the time attribute is set, the strength attribute is ignored.
        About silence : Use the mstts:silence element to insert pauses before or after text, or between two adjacent sentences.\ntype\tSpecifies where and how to add silence. 
            The following silence types are supported:\nLeading – Extra silence at the beginning of the text. The value that you set is added to the natural silence before the start of text. 
            Leading-exact – Silence at the beginning of the text. The value is an absolute silence length.
            Tailing – Extra silence at the end of text. The value that you set is added to the natural silence after the last word.\nTailing-exact – Silence at the end of the text. The value is an absolute silence length.
            Sentenceboundary – Extra silence between adjacent sentences. The actual silence length for this type includes the natural silence after the last word in the previous sentence, the value you set for this type, and the natural silence before the starting word in the next sentence.\nSentenceboundary-exact – Silence between adjacent sentences. The value is an absolute silence length.\nComma-exact – Silence at the comma in half-width or full-width format. The value is an absolute silence length.
            Semicolon-exact – Silence at the semicolon in half-width or full-width format. The value is an absolute silence length.
            Enumerationcomma-exact – Silence at the enumeration comma in full-width format. The value is an absolute silence length.\n\nAn absolute silence type (with the -exact suffix) replaces any otherwise natural leading or trailing silence.
            Absolute silence types take precedence over the corresponding non-absolute type. For example, if you set both Leading and Leading-exact types, the Leading-exact type takes effect.
            The WordBoundary event takes precedence over punctuation-related silence settings including Comma-exact, Semicolon-exact, or Enumerationcomma-exact. When you use both the WordBoundary event and punctuation-related silence settings, the punctuation-related silence settings don't take effect.
"""

USER_MSG = """The available information does not mention an option 5 for Fee Waive. However, you can contact the BDO Customer Contact Center at (02) 631-8000 for further assistance with fee waivers and other inquiries."""

def process_voice_tag(xml_string):
    # Remove markdown ``` and ssml if present
    xml_string = xml_string.replace("`ssml", "").replace("`xml", "").replace("`", "").strip()
    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError as e:
        print(f"Error parsing XML: {e}")
        return None, None
    
    # Parse the XML
    namespace = {"ssml": "http://www.w3.org/2001/10/synthesis"}  # Define the namespace
    root = ET.fromstring(xml_string)

    # Extract contents inside <voice> tag
    voice_element = root.find("ssml:voice", namespace)  # Find the <voice> tag
    voice_tag = ET.tostring(voice_element, encoding="unicode", method="xml")
    # Step 1: Attach voice tag to speech tag
    pretag = """<speak xmlns="http://www.w3.org/2001/10/synthesis" version="1.0" xml:lang="fil-PH">"""
    posttag = """</speak>"""
    speech_tag_string = f"{pretag}{voice_tag}{posttag}"

    # Step 2: Extract text and remove inner tags
    text_content = ''.join(voice_element.itertext())

    #remove extra whitespace
    text_content = " ".join(text_content.split())

    return speech_tag_string, text_content


def upload_audio_to_blob(local_file_path):
    storage_account_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL")
    container_name = os.getenv("AZURE_STORAGE_CONTAINER_NAME")
    if not storage_account_url or not container_name:
        return None

    blob_service_client = BlobServiceClient(account_url=storage_account_url, credential=credential)
    blob_name = os.path.basename(local_file_path)
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)

    with open(local_file_path, "rb") as data:
        blob_client.upload_blob(data, overwrite=True)

    blob_url = blob_client.url
    print(f"Blob URL: {blob_url}")
    return blob_url

def generate_audio_store(speechinput,str_prefix):
    speech_resource_id = os.getenv("AZURE_SPEECH_RESOURCE_ID")
    if not speech_resource_id:
        raise ValueError("Set AZURE_SPEECH_RESOURCE_ID to the Azure resource ID of your Speech or AI Services resource.")

    speech_region = os.getenv("AZURE_SPEECH_REGION")
    if not speech_region:
        raise ValueError("Set AZURE_SPEECH_REGION to the Speech resource region, for example swedencentral.")

    speech_token = credential.get_token("https://cognitiveservices.azure.com/.default").token
    speech_auth_token = f"aad#{speech_resource_id}#{speech_token}"
    speech_config = speechsdk.SpeechConfig(auth_token=speech_auth_token, region=speech_region)
    speech_config.speech_synthesis_voice_name = os.getenv("AZURE_SPEECH_VOICE", "fil-PH-BlessicaNeural")

    speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)

    speech_synthesis_result = speech_synthesizer.speak_ssml_async(speechinput).get()
    local_file_name = f"{str_prefix}-{uuid.uuid4()}.wav"
    local_file_path = os.path.join(AUDIO_OUTPUT_DIR, local_file_name)

    if speech_synthesis_result.reason == speechsdk.ResultReason.Canceled:
        cancellation_details = speech_synthesis_result.cancellation_details
        raise RuntimeError(
            f"Speech synthesis canceled: {cancellation_details.reason}. "
            f"Details: {cancellation_details.error_details or 'No additional details provided.'}"
        )

    if speech_synthesis_result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        raise RuntimeError(f"Unexpected speech synthesis result: {speech_synthesis_result.reason}")

    stream = speechsdk.AudioDataStream(speech_synthesis_result)
    stream.save_to_wav_file(local_file_path)

    storage_url = None
    storage_error = None
    try:
        storage_url = upload_audio_to_blob(local_file_path)
    except Exception as exc:
        storage_error = str(exc)
        print(f"Blob upload failed: {storage_error}")

    return {
        "local_audio_file": local_file_name,
        "storage_url": storage_url,
        "storage_error": storage_error,
    }


def extract_response_text(response):
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text

    output = getattr(response, "output", []) or []
    parts = []
    for item in output:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                parts.append(text)
    return "\n".join(parts)


def build_ssml(translated_text):
    escaped_text = escape((translated_text or "").strip())
    if not escaped_text:
        raise ValueError("The model returned empty translated text.")

    return (
        '<speak version="1.0" xml:lang="fil-PH" '
        'xmlns="http://www.w3.org/2001/10/synthesis" '
        'xmlns:mstts="https://www.w3.org/2001/mstts">'
        '<voice name="fil-PH-BlessicaNeural">'
        '<mstts:express-as style="customerservice">'
        f'<prosody rate="0%">{escaped_text}</prosody>'
        '</mstts:express-as>'
        '</voice>'
        '</speak>'
    )


def taglish_translate(usermsg):
    safe_prefix = re.sub(r"[^a-zA-Z0-9-]", "", (usermsg or "out")[:3]) or "out"

    response = client.responses.create(
        model=deployment,
        instructions=SYSTEM_PROMPT,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": usermsg},
                ],
            },
        ],
    )

    text_output = extract_response_text(response).strip()
    speech_output = build_ssml(text_output)
    audio_result = generate_audio_store(speech_output,safe_prefix)

    return {
        "speech_output": audio_result["storage_url"] or audio_result["local_audio_file"],
        "text_output": text_output,
        "local_audio_file": audio_result["local_audio_file"],
        "storage_url": audio_result["storage_url"],
        "storage_error": audio_result["storage_error"],
    }