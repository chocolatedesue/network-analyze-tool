import os

# API配置
API_KEY = os.getenv('API_KEY', '6be9eb101c')  # 可以从环境变量获取
BASE_URL = f'https://{API_KEY}.backend.sernes.cn'

# 网络配置
NETWORK_NAME = 'satnet_ospf_100'

# 网络参数
NETWORK_PARAMS = {
    "network_name": NETWORK_NAME,
    "network_description": "Satellite Network with OSPFv3",
    "constellation": {
        "name": "my_constellation",
        "type": "walker_delta",
        "orbit_altitude": 570,
        "orbit_inclination": 70,
        "orbit_num": 10,
        "sat_num_per_orbit": 10,
        "phase_shift": 1,
        "sat_isl_link_num": 4,
        "sat_gsl_link_num": 1,
        "sat_access_link_num": 0
    },
    "gs_set": [
        {
            "name": "gs_0",
            "latitude": 37.77,
            "longitude": -122.42,
            "elevation": 121.1,
            "gs_antenna_num": 1,
            "gs_antenna_angle": 25,
        },
        {
            "name": "gs_1",
            "latitude": 38.91,
            "longitude": -77.01,
            "elevation": 126.1,
            "gs_antenna_num": 1,
            "gs_antenna_angle": 25,
        }
    ],
}
