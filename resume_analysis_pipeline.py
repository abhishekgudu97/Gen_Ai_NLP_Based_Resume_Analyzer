import os
import re
import spacy
import pdfplumber
import docx
import pandas as pd
import tempfile
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
from urllib.parse import urlparse, parse_qs
from pathlib import Path

# Load spaCy language model
nlp = spacy.load("en_core_web_sm")

def analyze_resumes():
    """Main function to analyze resumes from a folder path or Google Drive link."""
    def extract_text_from_pdf(file_path):
        """Extract text content from a PDF file using pdfplumber."""
        try:
            with pdfplumber.open(file_path) as pdf:
                text = ''.join(page.extract_text() for page in pdf.pages if page.extract_text())
            return text
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return ""

    def extract_text_from_doc(file_path):
        """Extract text content from a DOCX file using python-docx."""
        try:
            doc = docx.Document(file_path)
            text = '\n'.join(paragraph.text for paragraph in doc.paragraphs)
            return text
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return ""

    def extract_email_and_phone(text):
        """Extract email and phone number from text using regex."""
        email = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
        phone = re.search(r"\b\d{10}\b", text)  # Matches 10-digit phone numbers
        return email.group(0) if email else None, phone.group(0) if phone else None

    def extract_education(text):
        """Extract educational qualifications from the text."""
        degrees = ["B.Sc", "M.Sc", "B.Tech", "M.Tech", "PhD", "MBA", "Bachelor", "Master", "Diploma"]
        found_degrees = [degree for degree in degrees if degree.lower() in text.lower()]
        return ", ".join(found_degrees)

    def extract_name(text):
        """Extract the name of the person from text using spaCy's Named Entity Recognition (NER)."""
        doc = nlp(text)
        persons = [ent.text for ent in doc.ents if ent.label_ == "PERSON"]
        if persons:
            return persons[0]
        return "Unknown"

    def extract_experience(text):
        """Try to extract years of experience from the text."""
        experience = re.search(r"\b\d{1,2}\s*(years?|yrs?)\b", text, re.IGNORECASE)
        return experience.group(0) if experience else "Not Mentioned"

    def extract_discipline(text):
        """Extract discipline/branch of study."""
        disciplines = ["Computer Science", "Electrical Engineering", "Mechanical Engineering", "Civil Engineering", "Biotechnology", "Chemistry", "Physics", "Mathematics", "Economics", "Business Administration"]
        found_disciplines = [discipline for discipline in disciplines if discipline.lower() in text.lower()]
        return ", ".join(found_disciplines) if found_disciplines else "Not Mentioned"

    def extract_passing_year(text):
        """Extract the passing year of the highest education level."""
        year = re.search(r"\b\d{4}\b", text)
        return year.group(0) if year else "Not Mentioned"

    def extract_skills(text):
        """Extract key skills from the text."""
        skills = ["Python", "Java", "C++", "Machine Learning", "Data Analysis", "Web Development", "SQL", "Project Management", "Communication", "Teamwork"]
        found_skills = [skill for skill in skills if skill.lower() in text.lower()]
        return ", ".join(found_skills) if found_skills else "Not Mentioned"

    def extract_cgpa_or_percentile(text):
        """Extract CGPA or percentile information from text."""
        cgpa = re.search(r"\b\d{1}\.\d{1,2}\b", text)  # Matches CGPA like 8.75 or 9.0
        percentile = re.search(r"\b\d{1,3}\s*%\b", text)  # Matches percentile like 85%
        if cgpa:
            return cgpa.group(0)
        elif percentile:
            return percentile.group(0)
        return "Not Mentioned"

    def extract_sporting_information(text):
        """Extract sporting or extracurricular information like certifications and internships."""
        sports_keywords = ["certification", "internship", "volunteer", "workshop", "training", "conference"]
        found_sports_info = [kw for kw in sports_keywords if kw.lower() in text.lower()]
        return ", ".join(found_sports_info) if found_sports_info else "Not Mentioned"

    def match_keywords(text, keywords):
        """Match specific keywords in the text and calculate a score."""
        matched_keywords = [kw for kw in keywords if kw.lower() in text.lower()]
        return len(matched_keywords), matched_keywords

    def generate_unique_filename(folder_path, base_name):
        """Generate a unique filename to avoid overwriting existing files."""
        count = 1
        while os.path.exists(os.path.join(folder_path, f"{base_name}{count}.csv")):
            count += 1
        return os.path.join(folder_path, f"{base_name}{count}.csv")

    def is_google_drive_link(link):
        """Check if the given path is a Google Drive folder link."""
        return "drive.google.com" in link

    def get_drive_service():
        """Authenticate and return the Google Drive API service."""
        SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
        creds = None
        token_path = 'token.pickle'
        credentials_path = 'credentials.json'
        if os.path.exists(token_path):
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(token_path, 'wb') as token:
                pickle.dump(creds, token)
        return build('drive', 'v3', credentials=creds)

    def download_google_drive_folder(link, download_path):
        """Download all files from a Google Drive folder."""
        folder_id = parse_qs(urlparse(link).query).get("id", [None])[0]
        if not folder_id:
            print("Invalid Google Drive folder link.")
            return []

        service = get_drive_service()
        results = service.files().list(q=f"'{folder_id}' in parents", fields="files(id, name)").execute()
        items = results.get('files', [])
        downloaded_files = []
        
        if not items:
            print("No files found in the Google Drive folder.")
            return []

        for item in items:
            request = service.files().get_media(fileId=item['id'])
            file_path = os.path.join(download_path, item['name'])
            with open(file_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
            downloaded_files.append(file_path)
        return downloaded_files

    folder_path_or_link = input("Enter the folder path or Google Drive link containing resumes: ")
    output_path = input("Enter the folder path to save the analysis CSV: ")
    gen_ai_keywords = input("Enter Gen AI keywords (comma-separated): ").split(",")
    ai_ml_keywords = input("Enter AI/ML keywords (comma-separated): ").split(",")
    
    # Temporary directory for Google Drive files
    temp_dir = tempfile.mkdtemp()
    resumes_path = folder_path_or_link

    if is_google_drive_link(folder_path_or_link):
        print("Google Drive link detected. Downloading files...")
        downloaded_files = download_google_drive_folder(folder_path_or_link, temp_dir)
        if not downloaded_files:
            print("No valid resumes found in the Google Drive folder.")
            return
        resumes_path = temp_dir

    # Process resumes as in the previous implementation
    data = []
    sl_no = 1

    for file_name in os.listdir(resumes_path):
        file_path = os.path.join(resumes_path, file_name)
        text = ""

        if file_name.endswith(".pdf"):
            print(f"Processing PDF: {file_name}")
            text = extract_text_from_pdf(file_path)
        elif file_name.endswith(".docx"):
            print(f"Processing DOCX: {file_name}")
            text = extract_text_from_doc(file_path)
        else:
            print(f"Skipping unsupported file: {file_name}")
            continue

        if text:
            email, phone = extract_email_and_phone(text)
            education = extract_education(text)
            name = extract_name(text)
            experience = extract_experience(text)
            discipline = extract_discipline(text)
            passing_year = extract_passing_year(text)
            skills = extract_skills(text)
            cgpa_or_percentile = extract_cgpa_or_percentile(text)
            sports_info = extract_sporting_information(text)
            gen_ai_score, gen_ai_matches = match_keywords(text, gen_ai_keywords)
            ai_ml_score, ai_ml_matches = match_keywords(text, ai_ml_keywords)

            data.append([
                sl_no, name, experience, email, phone, education,
                discipline, passing_year, skills, cgpa_or_percentile, sports_info,
                gen_ai_score, ai_ml_score,
                ", ".join(gen_ai_matches),
                ", ".join(ai_ml_matches)
            ])
            sl_no += 1

    columns = [
        "Sl No", "Name of Applicant", "Years of Experience", "Email ID", "Phone Number", "Education Details",
        "Discipline", "Passing Year", "Key Skills", "CGPA/Percentile", "Sporting/Certifications/Internships",
        "Gen AI Keyword Score", "AI/ML Keyword Score",
        "Gen AI Matching Keywords", "AI/ML Matching Keywords"
    ]

    output_file = generate_unique_filename(output_path, "resumes_analysis")
    pd.DataFrame(data, columns=columns).to_csv(output_file, index=False)
    print(f"Resume analysis saved to {output_file}")
