from phew import access_point, connect_to_wifi, is_connected_to_wifi, dns, server
from phew.template import render_template
import json
import machine
import os
import utime
import _thread
import gc

with open("config.json",'r') as f:
    config = json.load(f)

UID = ""
for b in machine.unique_id():
    UID += "{:02X}".format(b)
    
AP_NAME = "viperSetup"
#AP_DOMAIN = "viper-" + UID + ".setup"
AP_DOMAIN = "viper.setup"
AP_TEMPLATE_PATH = "/lib/ap_templates"
APP_TEMPLATE_PATH = "/lib/app_templates"
WIFI_FILE = "wifi.json"
WIFI_MAX_ATTEMPTS = 6

def machine_reset():
    utime.sleep(1)
    print("Resetting...")
    machine.reset()

def setup_mode():
    print("Entering setup mode...")
    
    def ap_index(request):
        if request.headers.get("host").lower() != AP_DOMAIN.lower():
            return render_template(f"{AP_TEMPLATE_PATH}/redirect.html", domain = AP_DOMAIN.lower())

        return render_template(f"{AP_TEMPLATE_PATH}/index.html")

    def ap_configure(request):
        print("Saving wifi credentials...")

        with open(WIFI_FILE, "w") as f:
            json.dump(request.form, f)
            f.close()
            

        # Reboot from new thread after we have responded to the user.
        _thread.start_new_thread(machine_reset, ())
        #code here for https://stackoverflow.com/questions/55138577/how-to-redirect-to-default-browser-from-captive-portal-cna-browser
        return render_template(f"{AP_TEMPLATE_PATH}/configured.html", ssid = request.form["ssid"])
        
    def ap_catch_all(request):
        if request.headers.get("host") != AP_DOMAIN:
            return render_template(f"{AP_TEMPLATE_PATH}/redirect.html", domain = AP_DOMAIN)

        return "Not found.", 404

    server.add_route("/", handler = ap_index, methods = ["GET"])
    server.add_route("/configure", handler = ap_configure, methods = ["POST"])
    server.set_callback(ap_catch_all)

    ap = access_point(AP_NAME)
    ip = ap.ifconfig()[0]
    dns.run_catchall(ip)
    print(ip)
def application_mode():
    print("Entering application mode.")
    onboard_led = machine.Pin(10, machine.Pin.OUT)

    def app_index(request):
        return render_template(f"{APP_TEMPLATE_PATH}/index.html")

    def app_toggle_led(request):
        onboard_led.toggle()
        return "OK"
    
    def app_get_temperature(request):
        # Not particularly reliable but uses built in hardware.
        # Demos how to incorporate senasor data into this application.
        # The front end polls this route and displays the output.
        # Replace code here with something else for a 'real' sensor.
        # Algorithm used here is from:
        # https://www.coderdojotc.org/micropython/advanced-labs/03-internal-temperature/
        sensor_temp = machine.ADC(4)
        reading = sensor_temp.read_u16() * (3.3 / (65535))
        temperature = 27 - (reading - 0.706)/0.001721
        return f"{round(temperature, 1)}"
    
    def app_reset(request):
        # Deleting the WIFI configuration file will cause the device to reboot as
        # the access point and request new configuration.
        os.remove(WIFI_FILE)
        # Reboot from new thread after we have responded to the user.
        _thread.start_new_thread(machine_reset, ())
        return render_template(f"{APP_TEMPLATE_PATH}/reset.html", access_point_ssid = AP_NAME)

    def app_catch_all(request):
        return "Not found.", 404
    
    def app_config(request):
        if request.method == "GET":
            return render_template(f"{APP_TEMPLATE_PATH}/config.html")
        elif request.method == "POST":
            print(request)
            with open("provision.json", "w") as f:
                json.dump(request.form,f)
            plantlist = []
            for x in range(int(request.form["plantnum"])):
                plantlist.append(str(UID + "_" + request.form["plantprefix"] + "_" + str(x+1)))
                #https://api.qrserver.com/v1/create-qr-code/?size=240x240&data=plant1
                #with open(str(UID + "_" + request.data["plantprefix"] + "_" + str(x+1)),'w')
            print(plantlist)
            
            with open("wifi.json",'r') as j:
                creds = json.load(j)
            
            global config
            config["NAME"] = request.form["unitname"]
            config["UID"] = UID
            config["USER"] = request.form["user"]
            config["CONTEXT"] = request.form["inout"]
            config["SSID"] = creds["ssid"]
            config["WIPASS"] = creds["password"]
            config["LOCALE"] = [request.form["lat"], request.form["long"]]
            config["PREFIX"] = request.form["plantprefix"]
            config["QTY"] = request.form["plantnum"]
            config["FIRSTRUN"] = True
            
            with open("config.json","w") as g:
                json.dump(config, g)
            
            return render_template(f"{APP_TEMPLATE_PATH}/qr.html", names = plantlist)
    
    def app_install(request):
        #Pull down the file manifest and call the OTA updater to begin installing logging software
        #even though no errors are expected, we use a try block here so that finally may be run after return
        '''
        import setupHelper
        try:
            setupHelper.updater()
            #_thread.start_new_thread(setupHelper.updater,())
        except Exception as error:
            print(error)
        '''
        print(gc.mem_free())
        global config
        del config
        gc.collect()
        print(gc.mem_free())
        
        try:
            #os.remove("main.py")
            #os.rename("setupHelper.py","main.py")
            #machine.reset()
            #import setupHelper
            #setupHelper.updater()
            
            import ugit
            ugit.pull_all(isconnected=True)
        except Exception as error:
            print(error)
        return render_template(f"{APP_TEMPLATE_PATH}/install.html")
        

    server.add_route("/", handler = app_index, methods = ["GET"])
    server.add_route("/toggle", handler = app_toggle_led, methods = ["GET"])
    server.add_route("/temperature", handler = app_get_temperature, methods = ["GET"])
    server.add_route("/reset", handler = app_reset, methods = ["GET"])
    # Add other routes for your application...
    server.add_route("/config", handler = app_config, methods = ["GET","POST"])
    server.add_route("/install", handler = app_install, methods = ["GET"])
    server.set_callback(app_catch_all)

# Figure out which mode to start up in...
try:
    os.stat(WIFI_FILE)

    # File was found, attempt to connect to wifi...
    with open(WIFI_FILE) as f:
        wifi_current_attempt = 1
        wifi_credentials = json.load(f)
        
        while (wifi_current_attempt < WIFI_MAX_ATTEMPTS):
            ip_address = connect_to_wifi(wifi_credentials["ssid"], wifi_credentials["password"])

            if is_connected_to_wifi():
                print(f"Connected to wifi, IP address {ip_address}")
                break
            else:
                wifi_current_attempt += 1
                
        if is_connected_to_wifi():
            application_mode()
        else:
            
            # Bad configuration, delete the credentials file, reboot
            # into setup mode to get new credentials from the user.
            print("Bad wifi connection!")
            print(wifi_credentials)
            os.remove(WIFI_FILE)
            machine_reset()

except Exception as error:
    # Either no wifi configuration file found, or something went wrong, 
    # so go into setup mode.
    setup_mode()
    print(error)

# Start the web server...
server.run()
