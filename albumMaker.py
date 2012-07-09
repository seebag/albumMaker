#!/usr/bin/env python
# -*- coding: iso-8859-15 -*-

import ConfigParser
import os
import logging
from iptcinfo import IPTCInfo
from PythonMagick import *
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
        splitxy = string.split('x')
        self.x = int(splitxy[0])
        self.y = int(splitxy[1])

class ImageAndPath:
    def __init__(self, path):
        self.path = path
        self.image = None

    def getPath(self):
        return self.path

    def getImage(self):
        if self.image == None:
            self.image = Image()
            self.image.read(self.path)
        return self.image

    def getExifOrientation(self):
        return int(self.getImage().attribute('EXIF:Orientation'))

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
                ratio = 1.*currentImage.size().width() / currentImage.size().height()
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
                    degree = 90
                elif orientation == 4:
                    degree = 270
                else:
                    logging.warning('EXIF orientation %i not supported yet : %s' % orientation)
                    degree = 0
                currentImage.rotate(degree)
                logging.info('Image rotated')


            # Resize image
            logging.debug('Resize image to %ix%i' % (sizex, sizey))
            currentImage.resize(Geometry(sizex, sizey))

            # Compute ratio deltas
            curx = currentImage.size().width()
            cury = currentImage.size().height()
            deltax = 0
            deltay = 0
            if sizex * cury != sizey * curx:
                # Not original ratio
                if slot.getOrientation() == 'h':
                    deltax = (sizex - (sizey * curx / cury)) / 2
                else:
                    deltay = (sizey - (sizex * cury / curx)) / 2
            print 'delta to apply %ix%i' % (deltax, deltay)

            # Insert image 
            drawableImage = DrawableCompositeImage(slot.getPosition().x + deltax,
            slot.getPosition().y + deltay, currentImage)
            imageSrc.draw(drawableImage)

            try:
                info = IPTCInfo(currentImageAndPath.getPath())
                title = info.data['caption/abstract']
                drawableText = DrawableText(slot.getTextPosition().x, slot.getTextPosition().y, title)
                drawableFont = DrawableFont(self.pageProperties.finalImageFont)
                drawablePointSize = DrawablePointSize(self.pageProperties.finalImageFontSize)
                imageSrc.draw(drawableFont, drawablePointSize, drawableText)
            except:
                logging.warning("No iptc data for " + currentImageAndPath.getPath())
                print 'Geometry(%i, %i, %i, %i)' % (slot.getTextPosition().x,
                                slot.getTextPosition().y, slot.getTextPosition().x + 500,
                                slot.getTextPosition().y 
                                                + 300)
                drawableText = DrawableText(slot.getTextPosition().x, slot.getTextPosition().y,
                'drawable')
                drawableFont = DrawableFont(self.pageProperties.finalImageFont)
                drawablePointSize = DrawablePointSize(self.pageProperties.finalImageFontSize)
                imageSrc.draw(drawableFont, drawablePointSize, drawableText)

            logging.info('Image "%s" added in layout %s' % (currentImageAndPath.getPath(), self.name))

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
    pageProperties.finalImageResolution = config.get('general', 'finalImage.resolution')
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
    (pageProperties, layouts) = parseConfig('firstTry.cfg')
    
    base = '/home/sebastien/Videos/Album nouveau Seb/'
    #images = [
    #ImageAndPath("/home/sebastien/Videos/Album nouveau Seb/10- Semaine de Noel en Belgique du 27 au 31 décembre (Bruges, cousine Marie, Bruxelles, Géocaching)  (6).JPG"),
    #ImageAndPath("/home/sebastien/Videos/Album nouveau Seb/10- Semaine de Noel en Belgique du 27 au 31 décembre (Bruges, cousine Marie, Bruxelles, Géocaching)  (7).JPG"),
    #ImageAndPath("/home/sebastien/Videos/Album nouveau Seb/10- Semaine de Noel en Belgique du 27 au 31 décembre (Bruges, cousine Marie, Bruxelles, Géocaching)  (8).JPG"),
    #]

    images = []
    for filename in natsorted(os.listdir(base)):
        if filename.endswith('.JPG'):
            images.append(ImageAndPath(base + filename))

    index = 0
    page = 0

    while index < len(images):
        pageImage = Image(pageProperties.finalImageResolution, 'white')

        (imageNumber, compatibleLayout) = Layout.getCompatibleLayout(layouts, images[index:])
        if compatibleLayout == None:
            print 'No layout compatible found'
            return

        compatibleLayout.render(pageImage, images[index:index+imageNumber])
        print 'Page %i has been rendered with image %i to %i with layout %s' % (page, index, index
        + imageNumber, compatibleLayout.name)
        page += 1
        index += imageNumber
        pageImage.write('images/page-%i.jpg' % page)
    
if __name__ == "__main__":
    main()

