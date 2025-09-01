import httpx
import anyio
import os
import typer
from loguru import logger
from config import API_KEY, BASE_URL, NETWORK_NAME, NETWORK_PARAMS

app = typer.Typer()

class APIClient:
    def __init__(self, base_url):
        self.base_url = base_url

    async def post(self, endpoint, json_data=None, files=None):
        async with httpx.AsyncClient() as client:
            url = self.base_url + endpoint
            if files:
                response = await client.post(url, files=files)
            else:
                response = await client.post(url, json=json_data)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"POST {endpoint} failed: {response.status_code}, {response.text}")
                return None

    async def get(self, endpoint, params=None):
        async with httpx.AsyncClient() as client:
            url = self.base_url + endpoint
            response = await client.get(url, params=params)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"GET {endpoint} failed: {response.status_code}, {response.text}")
                return None

async def create_network():
    client = APIClient(BASE_URL)
    logger.info("创建网络...")
    response = await client.post('/api/network/create/', json_data=NETWORK_PARAMS)
    if not response:
        logger.error("网络创建失败")
        return None

    logger.info("网络创建成功")
    network_id = response['network_id']
    logger.info(f"网络ID: {network_id}")

    # 上传配置文件
    config_zip_path = f'{NETWORK_NAME}.zip'
    if os.path.exists(config_zip_path):
        logger.info("上传配置文件...")
        with open(config_zip_path, 'rb') as f:
            files = {'file': (config_zip_path, f)}
            await client.post(f'/api/network/{network_id}/file/upload', files=files)
    else:
        logger.warning(f"配置文件 {config_zip_path} 不存在，跳过上传")

    return network_id

async def run_network(network_id: int):
    client = APIClient(BASE_URL)
    logger.info("启动网络...")
    await client.get(f'/api/network/{network_id}/run/')

    # 检查网络状态
    logger.info("检查网络状态...")
    while True:
        response = await client.get('/api/network/list', {'id': network_id})
        if response and response.get('data'):
            network_status = response['data'][0]['network_status']
            if network_status == 1:
                logger.info("网络启动成功")
                break
        await anyio.sleep(1)

async def delete_network(network_id: int):
    client = APIClient(BASE_URL)
    logger.info(f"删除网络 {network_id}...")
    
    # 获取网络状态
    response = await client.get('/api/network/list', {'id': network_id})
    if response and response.get('data') and response['data']:
        status = response['data'][0]['network_status']
        if status == 1:  # running
            await client.get(f'/api/network/{network_id}/destroy/')
        else:  # not running
            await client.get(f'/api/network/{network_id}/remove/')
    else:
        logger.error(f"无法获取网络 {network_id} 状态")
        return
    
    logger.info(f"网络 {network_id} 删除完成")

async def stop_network(network_id: int):
    client = APIClient(BASE_URL)
    logger.info(f"停止网络 {network_id}...")
    await client.get(f'/api/network/{network_id}/reset/')
    logger.info(f"网络 {network_id} 停止完成")

async def delete_all_networks_impl():
    client = APIClient(BASE_URL)
    logger.info("获取所有网络...")
    response = await client.get('/api/network/list')
    if response and response.get('data'):
        async with anyio.create_task_group() as tg:
            for net in response['data']:
                tg.start_soon(delete_network, net['network_id'])
    else:
        logger.info("没有网络需要删除")

async def stop_all_networks_impl():
    client = APIClient(BASE_URL)
    logger.info("获取所有网络...")
    response = await client.get('/api/network/list')
    if response and response.get('data'):
        async with anyio.create_task_group() as tg:
            for net in response['data']:
                if net['network_status'] == 1:  # running
                    tg.start_soon(stop_network, net['network_id'])
                else:
                    logger.info(f"网络 {net['network_id']} 已停止，跳过停止")
    else:
        logger.info("没有网络需要停止")

async def list_networks():
    client = APIClient(BASE_URL)
    response = await client.get('/api/network/list')
    if response and response.get('data'):
        for net in response['data']:
            logger.info(f"网络ID: {net['network_id']}, 状态: {net['network_status']}, 名称: {net['network_name']}")
    else:
        logger.info("没有网络")

@app.command()
def create():
    """创建网络"""
    network_id = anyio.run(create_network)
    if network_id:
        logger.info(f"使用 'uv run online-service/main.py run {network_id}' 来启动网络")

@app.command()
def run(network_id: int):
    """启动网络"""
    anyio.run(run_network, network_id)

@app.command()
def stop(network_id: int):
    """停止网络（重置）"""
    anyio.run(stop_network, network_id)

@app.command()
def delete(network_id: int):
    """删除指定网络"""
    anyio.run(delete_network, network_id)

@app.command()
def delete_all():
    """删除所有网络"""
    anyio.run(delete_all_networks_impl)

@app.command()
def stop_all():
    """停止所有运行中的网络"""
    anyio.run(stop_all_networks_impl)

@app.command()
def list():
    """列出所有网络"""
    anyio.run(list_networks)

if __name__ == "__main__":
    app()
