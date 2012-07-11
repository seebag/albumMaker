#!/usr/bin/env python
# -*- coding: iso-8859-15 -*-

import ConfigParser
import os
import logging
from iptcinfo import IPTCInfo
from PIL import Image, ImageDraw,ImageFont
from PIL.ExifTags import TAGS
from natsort import *


class Slot:
    def __init__(self, orientation, imagePosition, textPosition):
        self.orientation = orientation
        self.imagePosition = imagePosition
        self.textPosition = textPosition

    def getOrientation(self):
        return self.orientation

    def getPosition(self):
        return self.imagePosition

    def getTextPosition(self):
        return self.textPosition

class Size:
    def __init__(self, string):
        self.x = 0
        self.y = 0
        self.x2 = 0
        self.y2 = 0
        if string != 'auto':
            split1 = string.split('+')
            splitxy = split1[0].split('x')
            self.x = int(splitxy[0])
            self.y = int(splitxy[1])
            if len(split1) == 2:
                splitxy2 = split1[1].split('x')
                self.x2 = int(splitxy2[0])
                self.y2 = int(splitxy2[1])


    def getTuple(self):
        return (self.x, self.y)

class ImageAndPath:
    def __init__(self, path):
        self.path = path
        self.image = None

    def getPath(self):
        return self.path

    def getImage(self):
        if self.image == None:
            self.image = Image.open(self.path)
        return self.image

    def getExifOrientation(self):
        info = self.getImage()._getexif()
        if info != None:
            for tag, value in info.items():
                decoded = TAGS.get(tag, tag)
                if decoded == 'Orientation':
                    return value
        return 0

class Layout:
    def __init__(self, name, pageProperties):
        self.name = name
        self.pageProperties = pageProperties
        self.slots = []
        print 'Layout %s added' % name

    def addSlot(self, orientation, imagePosition, textPosition):
        self.slots.append(Slot(orientation, imagePosition, textPosition))
        print ' Slot with %s orientation added' % orientation

    def isCompatible(self, images):
        if len(images) != len(self.slots):
            return False
        i = 0
        for slot in self.slots:
            currentImageAndPath = images[i]
            i += 1
            currentImage = currentImageAndPath.getImage()
            orientation = currentImageAndPath.getExifOrientation()

            if orientation <= 1:
                # Use simple ratio
                ratio = 1.*currentImage.size[0] / currentImage.size[1]
                logging.debug('Detected ratio %f' % ratio)
                if ratio > 1:
                    detectedOrientation = 'h'
                elif ratio < 1:
                    detectedOrientation = 'v'
            else:
                # Use Exif orientation
                logging.debug('Detected exif orientation %i' % orientation)
                if orientation == 6 or orientation == 4:
                    detectedOrientation = 'v'
                else:
                    logging.warning('Not supported EXIF orientation : %i' % orientation)
                    detectedOrientation = 'h'

            logging.debug('Detected orientation %s for %s' % (detectedOrientation,
            currentImageAndPath.getPath()))

            if detectedOrientation != slot.getOrientation():
                return False

        return True



    """
    imageSrc : magick++ image src
    picturesPath : path of images
    """
    def render(self, imageSrc, images):
        i = 0
        for slot in self.slots:
            currentImageAndPath = images[i]
            i += 1
            currentImage = currentImageAndPath.getImage()

            if slot.getOrientation() == 'h':
                sizex = self.pageProperties.imageResolutionLong
                sizey = self.pageProperties.imageResolutionShort
            elif slot.getOrientation() == 'v':
                sizex = self.pageProperties.imageResolutionShort
                sizey = self.pageProperties.imageResolutionLong
            else:
                logging.warning('Not supported orientation: ' + slot.getOrientation())
                continue


            orientation = currentImageAndPath.getExifOrientation()
            if orientation > 1:
                if orientation == 6:
                    degree = Image.ROTATE_90
                elif orientation == 4:
                    degree = Image.ROTATE_270
                else:
                    logging.warning('EXIF orientation %i not supported yet : %s' % orientation)
                    degree = 0
                currentImage = currentImage.transpose(degree)
                logging.info('Image rotated')

            # Compute ratio deltas
            curx = currentImage.size[0]
            cury = currentImage.size[1]
            overheadx = 0
            overheady = 0

            if sizex * cury != sizey * curx:
                # Not original ratio
                if slot.getOrientation() == 'h':
                    overheadx = sizex - (sizey * curx / cury) 
                else:
                    overheady = sizey - (sizex * cury / curx)
            deltax = overheadx / 2
            deltay = overheady / 2
            print 'delta to apply %ix%i' % (deltax, deltay)
            print 'overhead to apply %ix%i' % (overheadx, overheady)

            # Resize image
            logging.debug('Resize image to %ix%i' % (sizex - overheadx, sizey - overheady))
            currentImage = currentImage.resize((sizex - overheadx, sizey - overheady),
            Image.ANTIALIAS)

            # Insert image 
            imageSrc.paste(currentImage, (slot.getPosition().x + deltax, slot.getPosition().y +
            deltay))
            title = ''
            try:
                info = IPTCInfo(currentImageAndPath.getPath())
                title = info.data['caption/abstract']
                if title == None:
                    title = ''

            except:
                logging.warning("No iptc data for " + currentImageAndPath.getPath())
                title = 'Texte bidon'

            d = ImageDraw.Draw(imageSrc)
            font = ImageFont.truetype(self.pageProperties.finalImageFont, self.pageProperties.finalImageFontSize)
            print 'Title = ' + title
            sizetext = d.textsize(title, font)
            deltatext = (sizex / 2) - (sizetext[0] / 2)
            if sizetext > sizex:
                logging.warning('Le texte est plus grand que la largeur de la photo !')
            if slot.getTextPosition().x == 0 and slot.getTextPosition().y == 0:
                # Auto mode
                if slot.getOrientation() == 'h':
                    positionx = slot.getPosition().x + deltatext
                    positiony = slot.getPosition().y + sizey + sizetext[1] * 0.5
                else:
                    logging.error('No automode support for vertical photo')

            else:        
                positionx = slot.getTextPosition().x
                positiony = slot.getTextPosition().y

            if slot.getTextPosition().x2 != 0:
                maxsizex = slot.getTextPosition().x2 - slot.getTextPosition().x
                print '****** Bounding box defined : %d' % maxsizex
            else:
                maxsizex = sizex

            lines = Layout.getLinesFromTitle(title, (maxsizex, 0), d, font)
            print lines
            lineindex = 0
            for line in lines:
                d.text((positionx, positiony + lineindex * sizetext[1] * 1.5), line, '#000000', font)
                lineindex += 1

            logging.info('Image "%s" added in layout %s' % (currentImageAndPath.getPath(), self.name))

    @staticmethod
    def getLinesFromTitle(title, boundingbox, draw, font):
        titletab = title.split(' ')
        lines = []
        line = ''
        oldline = ''
        for word in titletab:
            line += word + ' '
            if draw.textsize(line, font)[0] > boundingbox[0]:
                lines.append(oldline[0:len(oldline)-1])
                line = word + ' '
            oldline = line

        lines.append(oldline[0:len(oldline)-1])
        return lines

    @staticmethod
    def getCompatibleLayoutForOneImageNumber(layouts, images):
        for l in layouts:
            if l.isCompatible(images):
                return l
        return None

    @staticmethod
    def getCompatibleLayout(layouts, images):
        imageNumber = 3
        while imageNumber > 0:
            compatibleLayout = Layout.getCompatibleLayoutForOneImageNumber(layouts, images[0:imageNumber])
            if compatibleLayout != None:
                return (imageNumber, compatibleLayout)
            else:
                imageNumber -= 1

        logging.error('No layout compatible found')
        return (0, None)
        

class PageProperties:
    pass

def parseConfig(configFile):
    config = ConfigParser.RawConfigParser()
    config.read(configFile)
    pageProperties = PageProperties()
    layouts = []
    pageProperties.finalImageResolution = Size(config.get('general', 'finalImage.resolution'))
    pageProperties.finalImageFont = config.get('general', 'finalImage.font')
    pageProperties.finalImageFontSize = config.getint('general', 'finalImage.fontSize')
    pageProperties.imageResolutionLong = config.getint('general', 'image.default.resolutionLong')
    pageProperties.imageResolutionShort = config.getint('general', 'image.default.resolutionShort')
    
    for section in config.sections():
        if section.startswith('layout-'):
            l = Layout(section, pageProperties)
            layouts.append(l)
            slotsText = [None]*3
            for option in config.options(section):
                if option == 'photo.0':
                    slotsText[0] = option
                elif option == 'photo.1':
                    slotsText[1] = option
                elif option == 'photo.2':
                    slotsText[2] = option
            for label in slotsText:
                if label != None:
                    values = config.get(section, label).split(',')
                    l.addSlot(values[0].strip(), Size(values[1].strip()), Size(values[2].strip()))

    return (pageProperties, layouts)

def main():
    logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)
    (pageProperties, layouts) = parseConfig('configuration.cfg')
    
    base = '/home/sebastien/Videos/Album nouveau Seb/'
    #images = [
    #ImageAndPath("/home/sebastien/Videos/Album nouveau Seb/10- Semaine de Noel en Belgique du 27 au 31 décembre (Bruges, cousine Marie, Bruxelles, Géocaching)  (6).JPG"),
    #ImageAndPath("/home/sebastien/Videos/Album nouveau Seb/10- Semaine de Noel en Belgique du 27 au 31 décembre (Bruges, cousine Marie, Bruxelles, Géocaching)  (7).JPG"),
    #ImageAndPath("/home/sebastien/Videos/Album nouveau Seb/10- Semaine de Noel en Belgique du 27 au 31 décembre (Bruges, cousine Marie, Bruxelles, Géocaching)  (8).JPG"),
    #]
    images = [
    ImageAndPath("blackh.jpg"), #1
    ImageAndPath("blackh.jpg"),
    ImageAndPath("blackh.jpg"),
    ImageAndPath("blackv.jpg"), #2
    ImageAndPath("blackv.jpg"),
    ImageAndPath("blackh.jpg"), #3
    ImageAndPath("blackh.jpg"),
    ImageAndPath("blackv.jpg"), #5
    ImageAndPath("blackh.jpg"),
    ImageAndPath("blackh.jpg"), #4
    ImageAndPath("blackv.jpg"),
    ImageAndPath("blackh.jpg"), #6
    ]


    #images = []
    #for filename in natsorted(os.listdir(base)):
    #    if filename.endswith('.JPG'):
    #        images.append(ImageAndPath(base + filename))

    index = 0
    page = 0

    while index < len(images):
        pageImage = Image.new('RGB', pageProperties.finalImageResolution.getTuple(), '#ffffff')

        (imageNumber, compatibleLayout) = Layout.getCompatibleLayout(layouts, images[index:])
        if compatibleLayout == None:
            print 'No layout compatible found'
            return

        compatibleLayout.render(pageImage, images[index:index+imageNumber])
        print 'Page %i has been rendered with image %i to %i with layout %s' % (page, index, index
        + imageNumber, compatibleLayout.name)
        page += 1
        index += imageNumber
        pageImage.save('images/page-%i.png' % page)
    
if __name__ == "__main__":
    main()

