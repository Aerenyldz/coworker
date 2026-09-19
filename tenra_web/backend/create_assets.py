import os
from PIL import Image

SOURCE_IMG = r"C:\Users\ahmet\OneDrive\Desktop\coworker\Gemini_Generated_Image_f2y3ccf2y3ccf2y3.png"
TARGET_ICO = r"C:\Users\ahmet\OneDrive\Desktop\coworker\tenra_web\backend\tenra.ico"

def create_ico():
    try:
        if os.path.exists(SOURCE_IMG):
            img = Image.open(SOURCE_IMG)
            # Create a squarish image for ICO
            img = img.resize((256, 256))
            img.save(TARGET_ICO, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (32, 32)])
            print("ICO created successfully.")
        else:
            print("Source image for T icon not found.", SOURCE_IMG)
    except Exception as e:
        print("Failed to create ICO:", str(e))

if __name__ == '__main__':
    create_ico()
