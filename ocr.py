# import the necessary packages
from imutils.perspective import four_point_transform
import pytesseract
import argparse
import imutils
import cv2
import re
import numpy as np
import io
from PIL import Image, ImageEnhance, ImageFilter
import datetime

print(datetime.datetime.now())

# construct the argument parser and parse the arguments
ap = argparse.ArgumentParser()
ap.add_argument("-i", "--image", required=True, help="path to input image to be OCR'd")
ap.add_argument("-d", "--debug", type=int, default=1, help="whether or not we are visualizing each step of the pipeline")
ap.add_argument("-c", "--min-conf", type=int, default=0, help="minimum confidence value to filter weak text detection")

args = vars(ap.parse_args())

# load the input image from disk
orig = cv2.imread(args["image"])

# resize input image and compute the ratio of the *new* width to the *old* width
image = orig.copy()
image = imutils.resize(image, width=600)
ratio = orig.shape[1] / float(image.shape[1])

# convert the image to grayscale, blur it, and apply edge detection to reveal the outline of the input image
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
blurred = cv2.GaussianBlur(gray, (5, 5), 0)
edged = cv2.Canny(blurred, 30, 150)

# save outputs for troubleshooting
cv2.imwrite("/home/pi/output/1-gray.jpg", gray)
cv2.imwrite("/home/pi/output/2-blurred.jpg", blurred)
cv2.imwrite("/home/pi/output/3-edged.jpg", edged)

# detect contours in the edge map, sort them by size (in descending order), and grab the largest contours
# Use a copy of the image e.g. edged.copy() because findContours alters the image
cnts = cv2.findContours(edged.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
cnts = imutils.grab_contours(cnts)
cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:5]

# initialize a contour that corresponds to the input image outline
cardCnt = None

# loop over the contours
for c in cnts:
	# approximate the contour
	peri = cv2.arcLength(c, True)
	approx = cv2.approxPolyDP(c, 0.02 * peri, True)

	# if this is the first contour we've encountered that has four vertices, then we can assume we've found the input image
	if len(approx) == 4:
		cardCnt = approx
		break

height, width, channels = image.shape

# if the input image contour is empty then our script could not find the outline of the card
if cardCnt is None:
	print("Could not find outline.") # "Try debugging your edge detection and contour steps."

	# If no contours are found, assume the boundary is the contour so that we have some output
	cardCnt = np.array([[[0, 0]],[[0, height]],[[width, height]],[[width, 0]]], dtype=np.int32)

# Add a padding to improve OCR on text close to edges
padding = 20
cardCnt[0][0][0] = cardCnt[0][0][0] - padding # max(0, cardCnt[0][0][0] - padding)
cardCnt[0][0][1] = cardCnt[0][0][1] - padding # max(0, cardCnt[0][0][1] - padding)
cardCnt[1][0][0] = cardCnt[1][0][0] - padding # max(0, cardCnt[1][0][0] - padding)
cardCnt[1][0][1] = cardCnt[1][0][1] + padding # min(height, cardCnt[1][0][1] + padding)
cardCnt[2][0][0] = cardCnt[2][0][0] + padding # min(width, cardCnt[2][0][0] + padding)
cardCnt[2][0][1] = cardCnt[2][0][1] + padding # min(height, cardCnt[2][0][1] + padding)
cardCnt[3][0][0] = cardCnt[3][0][0] + padding # min(width, cardCnt[3][0][0] + padding)
cardCnt[3][0][1] = cardCnt[3][0][1] - padding # max(0, cardCnt[3][0][1] - padding)

print("\nContours: \n", cardCnt)

# draw the contour of the input image on the image
output = image.copy()
cv2.drawContours(output, [cardCnt], -1, (0, 255, 0), 2) # -1 signifies drawing all contours
cv2.imwrite("/home/pi/output/4-outline.jpg", output)

# apply a four-point perspective transform to the *original* image to obtain a top-down bird's-eye view of the input image
card = four_point_transform(orig, cardCnt.reshape(4, 2) * ratio)
cv2.imwrite("/home/pi/output/5-transformed.jpg", card)

# convert the input image from BGR to RGB channel ordering
rgb = cv2.cvtColor(card, cv2.COLOR_BGR2RGB)
cv2.imwrite("/home/pi/output/6-rgb.jpg", rgb)

# Enhance image to get clearer results from image_to_text
im = Image.open("/home/pi/output/6-rgb.jpg")
# im = im.convert('L')
im = im.convert("RGBA")
newimdata = []
datas = im.getdata()

for item in datas:
    if item[0] < 220 or item[1] < 220 or item[2] < 220:
        newimdata.append(item)
    else:
        newimdata.append((255, 255, 255))
im.putdata(newimdata)

im = im.filter(ImageFilter.MedianFilter()) # a little blur
enhancer = ImageEnhance.Contrast(im)
im = enhancer.enhance(2)
enhancer = ImageEnhance.Sharpness(im)
im = enhancer.enhance(2)
im = im.convert('1') # Convert image to black and white
im.save("/home/pi/output/7-enhanced.jpg")

# use Tesseract to OCR the image
text = pytesseract.image_to_string(im)

print("\n")
print("RAW OUTPUT")
print("=============")
print(text)

# use regular expressions to parse out phone numbers and email addresses from the input image
phoneNums = re.findall(r'[\+\(]?[1-9][0-9 .\-\(\)]{8,}[0-9]', text)
emails = re.findall(r"[a-z0-9\.\-+_]+@[a-z0-9\.\-+_]+\.[a-z]+", text)

# attempt to use regular expressions to parse out names
nameExp = r"\b([A-Z]\w+(?=[\s\-][A-Z])(?:[\s\-][A-Z]\w+)+)\b"
names = re.findall(nameExp, text)

# attempt to use regular expressions to parse out mailing addresses
mailExp = r"\d{1,4} [\w\s'\-,.]{1,} [0-9]{5}?"
mail_addresses = re.findall(mailExp, text)

# show the name header
print("\n")
print("NAME")
print("==============")

# assume name will be the first line and print it to our terminal
if names:
	name_var = names[0].strip()
	print(name_var)
else:
	name_var = ""

# show the mailing address header
print("\n")
print("ADDRESS")
print("======")

# loop over the detected mailing addresses and print them to our terminal
for addr in mail_addresses:
	print(addr.strip())

# show the phone numbers header
print("\n")
print("PHONE NUMBERS")
print("=============")

# loop over the detected phone numbers and print them to our terminal
for num in phoneNums:
	print(num.strip())

# show the email addresses header
print("\n")
print("EMAILS")
print("======")

# loop over the detected email addresses and print them to our terminal
for email in emails:
	print(email.strip())

print("\n")

# Write outputs to files
sender_text = open('/home/pi/output/ocr-output.txt', 'w+')
sender_text.writelines([str(datetime.datetime.now()),"\n\n"])
sender_text.writelines(text)
sender_text.close()