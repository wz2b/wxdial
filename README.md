# M5Dial Display for Temptest Weatherflow

# LICENSE

This project is copyright (c) 2026 Christopher Piggoott and carries
the [MIT License (MIT)](LICENSE).  Weather icons are based on
the TWC icon set, whose official web page has no license information.

# What is this?

The [MStack M5Dial](https://shop.m5stack.com/products/m5stack-dial-esp32-s3-smart-rotary-knob-w-1-28-round-touch-screen?variant=44064386875649) is a 1.28 inch rotary knob with an LCD touch screen.  This project uses circuitpython to
implement a Wi-Fi display for the [Templest Weather station](https://shop.tempest.earth/products/tempest).  It
implements a few screens including current weather and a wind history graph shown below.

![Screenshot](www/PXL_20260212_014522010.jpg)


# State of the Project

This project is a work in progress.  Currently I have a few problems with the UX lagging when
it gets busy doing Wi-Fi stuff.  I also implemented an MQTT input but the adafruit minimqtt is
not asynchronous so it causes lag.  I'm working on that.

The animations have been challenging.  A utility in the tools/ directory takes animated
gifs and turns them into tilegrids with each tilegrid independentyl compressed using
zlib.  This, unfortunately, causes memory churn and the tiny amount of RAM on the ESP32-S3
runs out.  I'm working on a solution to this - long term I may have to do away with the
fancy animated GIFs and just go to fixed ones.

