from PyPDF2 import PdfReader
import os

def get_pdf_pages(file_path):
    try:
        with open(file_path, 'rb') as file:
            reader = PdfReader(file)
            return len(reader.pages)
    except FileNotFoundError as e:
        print(f"File not found: {e}")
        return str(e)
    except Exception as e:
        print(f"An error occurred while getting PDF pages: {e}")
        return str(e)

def get_file_size(file_path):
    try:
        return os.path.getsize(file_path)
    except FileNotFoundError as e:
        print(f"File not found: {e}")
        return str(e)
    except Exception as e:
        print(f"An error occurred while getting file size: {e}")
        return str(e)