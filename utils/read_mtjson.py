import json
import sys

with open(sys.argv[1], 'r') as json_file:  
  data = json.load(json_file)
    
 #   print(json.dumps(data, indent=4))
    
 #   print('Name: ' + data["Header"]["Survey"])
 #   print('Website: ' + data["Header"]["Project"])
 #   print('From: ' + data["Header"]["Operator"])
 #   print('')

  #modify JSON file
  data["Header"]["Survey"] = "TEST"
  data["Header"]["Location"]["Latitude"] = 10

  print(json.dumps(data["Data"]["FREQ"]))

  
    
# write updated file
with open("out.json", "w") as json_file:
  json.dump(data, json_file, indent=2)
