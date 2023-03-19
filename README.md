# Company of Heores 3 Data
Data and icons on all Company of Heroes 3 units / stuff in a developer friendly format.

### Goal 
Goal of this repository is to gather all the data from the game Company of Heroes 3. For example data for all units. As well as tools and scripts for gathering this data from the game. We beliave that open sourcing all the data and tools can only help the game and community.
Once we have the data it's up to anyone to build any web-site or apps and work with this data. But let's put all our heads together 

### Convention
- All the data should be converted into .json files
- Please provide all the scripts / add manuals how you get the data
   - We can expect a lot of updates from developers. So we will need to run our scripts many times.
- We shall do git tags to mark patch changes 
- The tags are in this format 1.0.7-1, where 1.0.7 should match the game patch version -x (marks our revision)

### Contribution 
We are looking for more help! If you would like to contribute in any way. Please rech out ot us here in the issues / on the discord https://discord.gg/jRrnwqMfkr


## How to generate the data

1. Open Company of Heroes 3 Essence Editor (it's located in your COH3 instalaltion folder). 
2. One file ReferenceAttributes.sga `...\Company of Heroes 3\anvil\archives\ReferenceAttributes.sga`
3. Click on the attrib field, right click, extract   
![image](https://user-images.githubusercontent.com/8086995/226179199-855c6ea5-5336-4df9-941c-3dc4f4dc0ad0.png)

4. Extract it into folder `xml` of this repository. SHould look like this:  
![image](https://user-images.githubusercontent.com/8086995/226179287-a61f956c-ff99-456f-a679-faf1251ae18a.png)

5. Go into folder `cd scripts/xml-to-json`. 
6. Run Python script main.py. You need python3. Like this `python main.py`, you should see this result:  
![image](https://user-images.githubusercontent.com/8086995/226179423-711db84e-9cb4-41e7-92de-e2341b9130ba.png)

7. Check the folder, you should see exported files. 


## Changes after the patch
1. Generate teh data
2. Copy the .json files into folder `/data`
3. Make an MR with the changes 

The folder /data should always have the stable export of the data. 




### References:
Big thanks to all open source tools focused on Relic games.
https://github.com/RobinKa/RGDReader/tree/master/RRTexConverter
