from PIL import Image, ImageDraw, ImageFont

def generate_transparent_t_icon():
    # 256x256 transparent background
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    
    # Outer circle for smooth border
    # A beautiful teal glow circle
    d.ellipse([10, 10, 246, 246], fill=(20, 25, 30, 230), outline=(94, 235, 216, 255), width=6)
    
    # Let's draw a nice glowing T in the center
    # Using polygon for precise T shape
    # Center is 128, 128
    d.polygon([
        (78, 60), (178, 60),    # Top bar
        (178, 90), (143, 90),   # Right inner corner
        (143, 196), (113, 196), # Bottom stem
        (113, 90), (78, 90)     # Left inner corner
    ], fill=(94, 235, 216, 255))
    
    # Inner T details to make it look premium
    d.polygon([
        (88, 70), (168, 70), 
        (168, 80), (133, 80),
        (133, 186), (123, 186),
        (123, 80), (88, 80)
    ], fill=(210, 255, 250, 255))

    img.save(r"C:\Users\ahmet\OneDrive\Desktop\coworker\tenra_web\backend\tenra.ico", format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (32, 32)])

if __name__ == '__main__':
    generate_transparent_t_icon()
