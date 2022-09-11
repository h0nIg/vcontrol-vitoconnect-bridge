# vcontrol-vitoconnect-bridge

no support, just bunch of scripts and descriptions

## 
* connect Optolink-Kabel to /ttyUSB0
* add CP210x USB-UART adapter to raspberry PI (GPIO pins, connect TX to RX on USB, RX to TX)
* disable limited UART interface and turn off bluetooth (at least for raspberry PI 3)
```
/boot/config.txt
...
[all]
enable_uart=1
dtoverlay=pi3-disable-bt
```
* configure vcontrol to use TCP
```
<?xml version="1.0"?>
<V-Control xmlns:vcontrol="http://www.openv.de/vcontrol">
  <unix>
     <config>
        <serial>
                <tty>127.0.0.1:12345</tty>
        </serial>
```
