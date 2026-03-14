from PIL import Image

# Create a 64x64 black image
img = Image.new('RGB', (64, 64), color = 'black')
img.save('logo.png')
