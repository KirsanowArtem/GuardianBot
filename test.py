import os
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaFileUpload

# 🔑 Путь к credentials.json
SERVICE_ACCOUNT_FILE = "credentials.json"

# ⛓ Подключение к API
SCOPES = ['https://www.googleapis.com/auth/drive']
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
drive_service = build('drive', 'v3', credentials=credentials)

# 📂 ID папки в Google Диске (копируем из URL)
FOLDER_ID = "1PsqcOh0T3v6diNaId6uiMJawXLMG3rnm"


# 📌 Функция для получения списка файлов в папке
def list_files():
    results = drive_service.files().list(
        q=f"'{FOLDER_ID}' in parents",
        fields="files(id, name)"
    ).execute()

    files = results.get('files', [])
    print("📂 Files in the folder:")
    for file in files:
        print(f"📄 {file['name']} (ID: {file['id']})")

def upload_file(file_path, file_name):
    file_metadata = {
        "name": file_name,
        "parents": [FOLDER_ID]  # ID папки, в которую загружаем файл
    }
    media = MediaFileUpload(file_path, resumable=True)

    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()
    print(f"✅ File {file_name} uploaded! ID: {file.get('id')}")


# 📌 Запуск функции
if __name__ == "__main__":
    list_files()

# 📌 Загружаем файл
upload_file("data.json", "data.json")
upload_file("default_avatar.png", "default_avatar.png")
