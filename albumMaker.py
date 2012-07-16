#!/usr/bin/env python
# -*- coding: iso-8859-15 -*-
#
# Copyright (C) 2012 Sebastien Baguet. All rights reserved. Licensed under the new BSD license.
#

import ConfigParser
import os
import logging
import re
import argparse
import sys
from iptcinfo import IPTCInfo
from PIL import Image, ImageDraw,ImageFont,ImageOps
from PIL.ExifTags import TAGS
from natsort import *
from colorLogging import ColorizingStreamHandler


logger = logging.getLogger('albumMaker')

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
        self.align = 'left'
        if string != 'auto':
            split1 = string.split('+')
            splitxy = split1[0].split('x')
            self.x = int(splitxy[0])
            self.y = int(splitxy[1])
            if len(split1) > 1:
                splitxy2 = split1[1].split('x')
                self.x2 = int(splitxy2[0])
                self.y2 = int(splitxy2[1])
            if len(split1) > 2:
                self.align = split1[2]
        else:
            self.align = 'center'


    def getTuple(self):
        return (self.x, self.y)

class ImageAndPath:
    def __init__(self, path):
        self.path = path
        self.image = None

    def getPath(self):
        return self.path

    def getName(self):
        return os.path.basename(self.path)


    def getImage(self):
        if self.image == None:
            self.image = Image.open(self.path)
        return self.image

    def release(self):
        self.image = None

    def getExifOrientation(self):
        info = self.getImage()._getexif()
        if info != None:
            for tag, value in info.items():
                decoded = TAGS.get(tag, tag)
                if decoded == 'Orientation':
                    return value
        return 0

class Layout:
    allPicturesInserted = 0
    def __init__(self, name, pageProperties):
        self.name = name
        self.pageProperties = pageProperties
        self.slots = []
        logger.info('Layout %s added' % name)

    def addSlot(self, orientation, imagePosition, textPosition):
        self.slots.append(Slot(orientation, imagePosition, textPosition))
        logger.info(' Slot with %s orientation added' % orientation)

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
                logger.debug('Detected ratio %f' % ratio)
                if ratio > 1:
                    detectedOrientation = 'h'
                elif ratio < 1:
                    detectedOrientation = 'v'
            else:
                # Use Exif orientation
                logger.debug('Detected exif orientation %i' % orientation)
                if orientation == 6 or orientation == 4:
                    detectedOrientation = 'v'
                else:
                    logger.warning('Not supported EXIF orientation : %i' % orientation)
                    detectedOrientation = 'h'

            logger.debug('Detected orientation %s for %s' % (detectedOrientation,
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
                logger.warning('Not supported orientation: ' + slot.getOrientation())
                continue


            orientation = currentImageAndPath.getExifOrientation()
            if orientation > 1:
                if orientation == 6:
                    degree = Image.ROTATE_270
                elif orientation == 4:
                    degree = Image.ROTATE_90
                else:
                    logger.warning('EXIF orientation %i not supported yet : %s' % orientation)
                    degree = 0
                currentImage = currentImage.transpose(degree)
                logger.info('Image rotated')

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
            logger.debug('delta to apply %ix%i' % (deltax, deltay))

            # Resize image
            logger.debug('Resize image to %ix%i' % (sizex - overheadx, sizey - overheady))
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
                logger.warning("No comments for '%s'" % currentImageAndPath.getName())
                title = 'Texte bidon'

            d = ImageDraw.Draw(imageSrc)
            font = ImageFont.truetype(self.pageProperties.finalImageFont, self.pageProperties.finalImageFontSize)
            logger.debug('Title = ' + title)
            automode = slot.getTextPosition().x == 0 and slot.getTextPosition().y == 0
            if automode:
                # Auto mode
                if slot.getOrientation() == 'h':
                    positionx = slot.getPosition().x
                    positiony = slot.getPosition().y + sizey + 30
                else:
                    logger.error('No automode support for vertical photo')
            else:        
                positionx = slot.getTextPosition().x
                positiony = slot.getTextPosition().y

            if slot.getTextPosition().x2 != 0:
                maxsizex = slot.getTextPosition().x2 - slot.getTextPosition().x
            else:
                maxsizex = sizex

            lines = Layout.getLinesFromTitle(title, (maxsizex, 0), d, font)
            if automode and len(lines) > 1:
                logger.warning('Le texte est plus grand que la largeur de la photo !')
            lineindex = 0
            for line in lines:
                text = line[0]
                textsize = line[1]
                if slot.getTextPosition().align == 'left':
                    deltatextx = 0
                elif slot.getTextPosition().align == 'center':
                    deltatextx = maxsizex / 2 - textsize[0] / 2
                elif slot.getTextPosition().align == 'right':
                    deltatextx = maxsizex - textsize[0]
                else:
                    logger.warning('Undefined %s centering' % slot.getTextPosition().align)
                    deltatextx = 0
                d.text((positionx + deltatextx, positiony + lineindex * textsize[1] * 1.5), text, '#000000', font)
                logger.debug("Writing text '%s' of size %ix%i at %ix%i align=%s" % (text,
                textsize[0], textsize[1], positionx +
                deltatextx, positiony + lineindex * textsize[1] * 1.5,
                slot.getTextPosition().align))
                lineindex += 1

            logger.info("Image '%s' added" % currentImageAndPath.getName())
            Layout.allPicturesInserted += 1
            currentImageAndPath.release()

    @staticmethod
    def getLinesFromTitle(title, boundingbox, draw, font):
        titletab = title.split(' ')
        lines = []
        line = ''
        oldline = ''
        oldtextsize = 0
        for word in titletab:
            line += word + ' '
            textsize = draw.textsize(line, font)
            if textsize[0] > boundingbox[0]:
                lines.append((oldline[0:len(oldline)-1], oldtextsize))
                line = word + ' '
            oldline = line
            oldtextsize = textsize

        lines.append((oldline[0:len(oldline)-1], oldtextsize))
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

        logger.error('No layout compatible found')
        return (0, None)

def drawBookmark(image, chapterNumber, chapterName, pageProperties):
    positionx = pageProperties.finalImageResolution.x - pageProperties.bookmarksize.x
    positiony = int(100 + chapterNumber * pageProperties.bookmarksize.y * 1.2)
    color = '#' + pageProperties.indexColors[chapterNumber % len(pageProperties.indexColors)]

    draw = ImageDraw.Draw(image)
    draw.rectangle([(positionx, positiony), (positionx + pageProperties.bookmarksize.x,
    positiony + pageProperties.bookmarksize.y)], fill=color)
    if chapterName != '':
        logger.info("Printing chapter '%s' title" % chapterName)
        font = ImageFont.truetype(pageProperties.bookmarkFont, pageProperties.bookmarkFontSize)
        size = draw.textsize(chapterName, font)
        mask=Image.new('L', size)
        drawImg = ImageDraw.Draw(mask)
        drawImg.text((0,0), chapterName, 255, font)
        m2 = mask.rotate(90)
        image.paste(ImageOps.colorize(m2, (0,0,0), (0,0,0)), (positionx +
        pageProperties.bookmarksize.x / 2 - size[1] / 2,100),  m2)


def renderIndex(image, chapterList, chapters, pageProperties):
    deltax = 200
    for chapterNumber in chapters:
        chapterName = chapterList[chapterNumber]
        font = ImageFont.truetype(pageProperties.bookmarkFont, pageProperties.bookmarkFontSize)
        draw = ImageDraw.Draw(image)

        thumbnailImage = chapters[chapterNumber][0].getImage()
        thumbnailImage = thumbnailImage.resize((240, 160), Image.ANTIALIAS)
        image.paste(thumbnailImage, (deltax, int(100 + chapterNumber * pageProperties.bookmarksize.y
        * 1.2)))

        size = draw.textsize(chapterName, font)
        positiony = int(100 + chapterNumber * pageProperties.bookmarksize.y * 1.2 +
        pageProperties.bookmarksize.y / 2 - size[1] / 2) 
        draw.text((deltax + 270, positiony), chapterName, '#000000', font)
        drawBookmark(image, chapterNumber, '', pageProperties)


class PageProperties:
    pass

def parseConfig(configFile):
    logger.info("Parsing configuration")
    config = ConfigParser.RawConfigParser()
    config.read(configFile)
    pageProperties = PageProperties()
    layouts = []
    pageProperties.finalImageResolution = Size(config.get('general', 'finalImage.resolution'))
    pageProperties.finalImageFont = config.get('general', 'finalImage.font')
    pageProperties.finalImageFontSize = config.getint('general', 'finalImage.fontSize')
    pageProperties.finalImageBackgroundColor = config.get('general', 'finalImage.backgroundColor')
    pageProperties.imageResolutionLong = config.getint('general', 'image.default.resolutionLong')
    pageProperties.imageResolutionShort = config.getint('general', 'image.default.resolutionShort')
    pageProperties.bookmarksize = Size(config.get('general', 'index.bookmark.size'))
    pageProperties.bookmarkFont = config.get('general', 'index.bookmark.font')
    pageProperties.bookmarkFontSize = config.getint('general', 'index.bookmark.fontSize')
    pageProperties.indexColors = [ ]
    for colors in config.get('general',  'index.colors').split(','):
        pageProperties.indexColors.append(colors.strip())

    
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

    logger.info("Parsing done")
    return (pageProperties, layouts)

def main():
    parser = argparse.ArgumentParser(description='Make album from single photos')
    parser.add_argument('inputdir', nargs=1)
    parser.add_argument('-o', '--out', dest='outputDirectory')
    parser.add_argument('--testBlack', dest='testBlack', action='store_const', const=True,
    default=False)
    parser.add_argument('--testChapter', dest='testChapter', action='store_const', const=True,
    default=False)
    parser.add_argument('--debug', action='store_const', const=True, default=False)
    args = vars(parser.parse_args())

    logger.addHandler(ColorizingStreamHandler())

    if args['debug']:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)


    logger.info("Starting albumMaker")

    inputdir = args['inputdir'][0] + '/'
    if args['outputDirectory'] != None:
        outputdir = args['outputDirectory'] + '/'
    else:
        outputdir = inputdir + '/out/'

    logger.info("   inputdir = %s" % inputdir)
    logger.info("   outputdir = %s" % outputdir)

    (pageProperties, layouts) = parseConfig('configuration.cfg')

    if args['testBlack']:
        imgv = ImageAndPath("ressources/blackv.jpg")
        imgh = ImageAndPath("ressources/blackh.jpg")
        chapters = {
        1 : [
        imgh, imgh, imgh, #1
        imgv, imgv, #2
        imgh, imgh, #3
        imgv, imgh, #5
        imgh, imgv, #4
        imgh, #6
        ],
        2 : [
        imgv, #7
        ]
        }
        chapterList = {
        1 : 'Chapitre 1',
        2 : 'Chapitre 2',
        }
    elif args['testChapter']:
        img =  [ ImageAndPath("ressources/blackh.jpg") ]
        chapters = { }
        chapterList = { }
        for i in range(0, 20):
            chapters[i] = img
            chapterList[i] = 'Chapitre %i' % i
    else:
        chapterList = { }
        chapters = { }

        allimages = []
        for filename in natsorted(os.listdir(inputdir)):
            if filename.endswith('.JPG') or filename.endswith('.jpg'):
                allimages.append(ImageAndPath(inputdir + filename))
        for i in allimages:
            id = re.match(r'.*/(?P<chapter>\d+)-(?P<chapterName>.*)\((?P<number>\d+)\).*', i.getPath()).groupdict()
            if not chapters.has_key(int(id['chapter'])):
                chapters[int(id['chapter'])] = []
                chapterList[int(id['chapter'])] = id['chapterName'].strip().decode('utf-8')
            chapters[int(id['chapter'])].append(i)


    logger.info('Starting index rendering')
    page = 0
    pageImage = Image.new('RGB', pageProperties.finalImageResolution.getTuple(), '#' +
    pageProperties.finalImageBackgroundColor)
    renderIndex(pageImage, chapterList, chapters, pageProperties)
    pageImage.save('%s/page-%i.png' % (outputdir, page))
    logger.info('Index rendered')

    page = 1
    index = 0
    for chapterNumber in chapters:
        images = chapters[chapterNumber]
        chapterName = chapterList[chapterNumber]
        logger.info(" ** Starting chapter '%s'" % chapterName)
        index = 0
        while index < len(images):
            logger.info('   > Starting rendering page %i' % page)
            pageImage = Image.new('RGB', pageProperties.finalImageResolution.getTuple(), '#' +
            pageProperties.finalImageBackgroundColor)

            if index == 0:
                drawBookmark(pageImage, chapterNumber, chapterName, pageProperties)
            else:
                drawBookmark(pageImage, chapterNumber, '', pageProperties)

            (imageNumber, compatibleLayout) = Layout.getCompatibleLayout(layouts, images[index:])
            if compatibleLayout == None:
                logging.error('No layout compatible found')
                return

            compatibleLayout.render(pageImage, images[index:index+imageNumber])

            pageImage.save('%s/page-%i.png' % (outputdir, page))

            logger.info(' ==> Page %i has been rendered with image %i to %i with layout %s' % (page, index, index
            + imageNumber, compatibleLayout.name))

            page += 1
            index += imageNumber
    logger.info('%i pictures has been rendered in %i pages' % (Layout.allPicturesInserted, page))
    
if __name__ == "__main__":
    main()

