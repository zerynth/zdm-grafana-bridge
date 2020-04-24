import flask
import requests
from datetime import datetime
from json import dumps
import pytz

JWT="!!! YOUR JWT TOKEN HERE !!!"
workspace_id="!!! YOUR WORKSPACE ID !!!"

header={}

app=flask.Flask("grafanaRequests")
URL="https://api.zdm.zerynth.com/v1/tsmanager/workspace/"+workspace_id+"/"
DEVICEURL="https://api.zdm.zerynth.com/v1/workspace/"+workspace_id
header['Authorization']='Bearer ' + JWT


#getTable and getTimeSeries are the only function you need to change



#this function returns a dictionary that rappresents a Table
#For each column is given a name (text) and a type
def getTable(tag,response,filter):
    columns=[]
    rows=[]
    columns.append({"text":"Date","type":"time"}) #column 0

    if (tag!="tag4"):
        columns.append({"text":"value","type":"number"}) #column 1
        for data in response:
            if(filter==None or filter==data["device_id"]):
                timestamp=toUnixTimeStamp(data["timestamp_device"])*1000 #milliseconds from epoch
                value=data["payload"]["value"]
                rows.append([timestamp,value])

    else:
        columns.append({"text":"temperature","type":"number"}) #column 1
        columns.append({"text":"pressure","type":"number"}) #column 2
        for data in response:
            if(filter==None or filter==data["device_id"]):
                timestamp=toUnixTimeStamp(data["timestamp_device"])*1000 #milliseconds from epoch
                temp=data["payload"]["temp"]
                pressure=data["payload"]["pressure"]
                rows.append([timestamp,temp,pressure])

    return {"columns":columns,"rows":rows,"type":"table"}


#this function returns a list of timeseries created by data received from Zerynth ZDM
#each timeseries is a dictionary where the key "target" is the name of the value plotted and
#datapoints is a list that cointains coordinates in the form of [value,timestamp]
#For a query on a single metric, multiples timeseries can be returned (as in the case of tag4)
def getTimeSeries(tag,response,filter):
    result=[]
    if (tag!="tag4"):
        #in tag1, tag2 and tag3 payload={"value":x}
        datapoints=[]
        for data in response:
            if(filter==None or filter==data["device_id"]):
                timestamp=toUnixTimeStamp(data["timestamp_device"])*1000 #milliseconds from epoch
                value=data["payload"]["value"]
                datapoints.append([value,timestamp])
        result.append({"target":tag,"datapoints":datapoints})
    else:
        #in tag4, payload={"temp":x,"pressure":y}
        temperatureDatapoints=[]
        pressureDatapoints=[]
        for data in response:
            if(filter==None or filter==data["device_id"]):
                timestamp=toUnixTimeStamp(data["timestamp_device"])*1000 #milliseconds from epoch
                temperature=data["payload"]["temp"]
                pressure=data["payload"]["pressure"]
                temperatureDatapoints.append([temperature,timestamp])
                pressureDatapoints.append([pressure,timestamp])
                #two different datapoints for temperature and pressure
        result.append({"target":"tag4_temperature","datapoints":temperatureDatapoints})  #timeserie for temperature
        result.append({"target":"tag4_pressure","datapoints":pressureDatapoints}) #timeserie for pressure
            
    return result




#error class, set status code value
class InvalidConnection(Exception):
    status_code = 500

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        return rv

#Set error handler
@app.errorhandler(InvalidConnection)
def handle_invalid_usage(error):
    response = flask.jsonify(error.to_dict())
    response.status_code = error.status_code
    return response

    
#convert data from SimpleJson format into the one used for Zerynth ZDM 
def toZerynthFormat(string):
    date=datetime.strptime(string,"%Y-%m-%dT%H:%M:%S.%fZ")
    return date.strftime("%Y-%m-%dT%H:%M:%SZ")

#convert data in unix timestamp (seconds from EPOCH)
def toUnixTimeStamp(string):
    date=datetime.strptime(string,"%Y-%m-%dT%H:%M:%S")
    date=pytz.utc.localize(date)
    return date.timestamp()

#test route to see if connection is working
@app.route("/",methods=['GET'])
def test():
    response=requests.get(DEVICEURL,headers=header)
    if(response.ok==True):
        return "OK"
    else:
        raise InvalidConnection("couldn't connect to Zerynth ZDM")


#this route returns all tags in a workspace as metrics for queries in Grafana
@app.route("/search",methods=["GET","POST"])
def search():
    requestURL=URL+"tags"
    response=requests.get(requestURL,headers=header)
    data=response.json()
    return dumps(data["tags"])


#this route returns a query result from grafana
@app.route("/query",methods=["GET","POST"])
def query():
    parameters=flask.request.get_json()
    start=toZerynthFormat(parameters["range"]["from"])
    end=toZerynthFormat(parameters["range"]["to"])
    filters=parameters["adhocFilters"]
    device_id=None
    for el in filters: #get ad Hoc Filter from query request, returns empty string if more than a filter on device_id
        if(el["key"]=="device_id" and device_id==None):
            device_id=el["value"]
        elif(el["key"]=="device_id" and device_id!=el["value"]):
            device_id=""
    result=[]
    for target in parameters["targets"]: #a single query request can contains multiple targets
        tag=target["target"]
        requestURL=URL+"tag/"+tag+"?start="+start+"&end="+end+"&size=-1"+"&sort=timestamp_device"
        response=requests.get(requestURL,headers=header)
        if(target["type"]=="timeserie"):
            #if an error occurs while creating a timeseries, returns a blank timeseries
            try:
                timeseries=getTimeSeries(tag,response.json()["result"],device_id)
            except :
                timeseries=[{"target":tag,"datapoints":[]}]

            for serie in timeseries:
                result.append(serie)
        else:
            #if an error occurs while creating a table, returns a blank table
            try:
                table=getTable(tag,response.json()["result"],device_id)
            except:
                table={"columns":[],"rows":[],"type":"table"}
            result.append(table)
    return dumps(result)

@app.route("/annotations",methods=["GET","POST"])
def annotations():
    return {}

#allows you to filter by device_id
@app.route("/tag-keys",methods=["GET","POST"])
def tagKeys():
    return dumps([{"type":"string","text":"device_id"}])

#this route returns the list of device_id
@app.route("/tag-values",methods=["GET","POST"])
def tagValues():
    deviceList=[]
    parameters=flask.request.get_json()
    if(parameters["key"]=="device_id"):
        response=requests.get(DEVICEURL,headers=header)
        data=response.json()
        for fleet in data["workspace"]["fleets"]:
            for device in fleet["devices"]:
                deviceList.append({"text":device["id"]})
    return dumps(deviceList)

app.run()