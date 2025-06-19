# 尝试读取数据从工厂线
# Endpoint: opc.tcp://SPL-VMKEPOPCF03.SHIMANOACE.LOCAL:49320

# node : HTSBON01_BN01
# 检测到篮子时，此信号为 1
# LOAD_BSK_DETC = This signal is 1 when a basket is detected in the camera position. 
# 当篮子中装有物料时，此信号为 1。
# LOAD_BSK_V_MATL = This signal is 1 when a basket is loaded with material
# 物料批次 ID
# LOT_01_LOAD = This the string for Material Lot ID 
# 位于摄像头下方的篮子的 ID。
# LOT_01_LOAD_BSK_01 = This is the ID of the basket positioned under camera.

# 当 LOAD_BSK_DETC 和 LOAD_BSK_V_MATL 都为 1 时，延时 5 秒，触发相机开始缺陷检测。
# 读取 LOT_01_LOAD 和 LOT_01_LOAD_BSK_01 并将其标记在所捕获的图像上。同时分配 1 个图像 ID。
# When both LOAD_BSK_DETC and LOAD_BSK_V_MATL = 1, delay for 5 secs , then trigger camera to start defect detection. Read LOT_01_LOAD and LOT_01_LOAD_BSK_01 and label it on the images captured. Assign 1 image ID as well. 

# 当 LOAD_BSK_DETC =1 且 LOAD_BSK_V_MATL = 0 时，延时 5 秒，触发相机开始缺陷检测。
# 空篮检测（检查篮子中卡住的任何零件）。将其标记在所捕获的图像上。同时分配 1 个图像 ID。
# when LOAD_BSK_DETC =1 , and LOAD_BSK_V_MATL = 0, trigger camera for empty basket detection ( to check any parts stuck in backet). 

import asyncio
from asyncua import Client, ua

async def read_opc_ua_endpoint(endpoint_url):
    try:
        async with Client(url=endpoint_url) as client:
            root = client.nodes.root
            objects = await root.get_children()
            for obj in objects:
                children = await obj.get_children()
                for child in children:
                    try:
                        # Check if the child is a variable
                        node = client.get_node(child)  # Get the node object
                        browse_name = await node.read_browse_name() # Get the browse name
                        node_class = await node.read_node_class() # Get node class
                        if node_class == ua.NodeClass.Variable:
                            # Read the value of the variable
                            value = await node.read_value()
                            print(f"Found variable: {browse_name}, Value: {value}")
                            return value  # Return the first value found

                    except Exception as e:
                        print(f"Error reading child {child}: {e}")

            print("No variables found on the server.")
            return None

    except Exception as e:
        print(f"Error connecting to or reading from the OPC UA server: {e}")
        return None



async def main():
    endpoint_url = "opc.tcp://SPL-VMKEPOPCF03.SHIMANOACE.LOCAL:49320" 

    value = await read_opc_ua_endpoint(endpoint_url)

    if value is not None:
        print(f"The value read was: {value}")

if __name__ == "__main__":
    asyncio.run(main())