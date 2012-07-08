#!/usr/bin/env python

import ConfigParser
from iptcinfo import IPTCInfo
from PythonMagick import *

imagedefaultresolutionLong = 300
imagedefaultresolutionShort = 200

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
        print 'images.len = %i, slots.len=%i' % (len(images), len(self.slots))
        if len(images) != len(self.slots):
            return False
        i = 0
        for slot in self.slots:
            currentImageAndPath = images[i]
            i += 1
            currentImage = currentImageAndPath.getImage()
            ratio = 1.*currentImage.size().width() / currentImage.size().height()
            print ratio
            if ratio > 1 and slot.getOrientation() == 'h':
                if ratio > 1.4 or ratio < 1.3:
                    print 'Not supported ratio : ' + ratio
                pass 
            elif ratio < 1 and slot.getOrientation() == 'v':
                if ratio != 0.75:
                    print 'Not supported ratio : ' + ratio
                pass
            else:
                return False
        return True

    """
    imageSrc : magick++ image src
    picturesPath : path of images
    """
    def render(self, imageSrc, images):
        i = 0
        for slot in self.slots:
            print images
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
                print 'Not supported orientation: ' + slot.getOrientation()
                continue

            if currentImage.attribute('EXIF:Orientation') != '1':
                print 'EXIF orientation not supported yet'

            currentImage.resize(Geometry(sizex, sizey))
            imageSrc.composite(currentImage, slot.getPosition().x, slot.getPosition().y)

            try:
                info = IPTCInfo(currentImageAndPath.getPath())
                title = info.data['caption/abstract']
                drawableText = DrawableText(slot.getTextPosition().x, slot.getTextPosition().y, title)
                imageSrc.draw(drawableText)
            except:
                print "No iptc data for " + currentImageAndPath.getPath()

            print 'Image "%s" added in layout' % currentImageAndPath.getPath()

class PageProperties:
    pass
        
def parseFile():
    pass



def main():
    configFile = 'firstTry.cfg'
    config = ConfigParser.RawConfigParser()
    config.read(configFile)
    pageProperties = PageProperties()
    layouts = []
    pageProperties.finalImageResolution = config.get('general', 'finalImage.resolution')
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

    
    base = '/home/sebastien/Videos/Album nouveau Seb/'
    images = [
    ImageAndPath(base + "1- We Disney 24-25 septembre et rencontre avec didier (1).JPG"), 
    ImageAndPath(base + "1- We Disney 24-25 septembre et rencontre avec didier (2).JPG"), 
    ImageAndPath(base + "1- We Disney 24-25 septembre et rencontre avec didier (3).JPG"), 
    ImageAndPath(base + "1- We Disney 24-25 septembre et rencontre avec didier (4).JPG"), 
    ImageAndPath(base + "1- We Disney 24-25 septembre et rencontre avec didier (5).JPG")]
    allImages = []

    index = 0
    page = 0

    while index < len(images):
        big = Image(pageProperties.finalImageResolution, 'white')
        allImages.append(big)
        compatibleLayout = None
        imageNumber = 3
        for l in layouts:
            if l.isCompatible(images[index:index+imageNumber]):
                compatibleLayout = l
                break
        if compatibleLayout == None:
            print 'Trying with only two slots'
            imageNumber = 2
            for l in layouts:
                if l.isCompatible(images[index:index+imageNumber]):
                    compatibleLayout = l
                    break

        if compatibleLayout == None:
            print 'No layout compatible found'
            return

        compatibleLayout.render(big, images[index:index+imageNumber])
        print 'Page %i has been rendered with image %i to %i with layout %s' % (page, index, index
        + imageNumber, compatibleLayout.name)
        page += 1
        index += imageNumber
    
    for image in allImages:
        image.display()

if __name__ == "__main__":
    main()

