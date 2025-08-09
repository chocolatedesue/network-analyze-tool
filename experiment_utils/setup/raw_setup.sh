
#!/bin/bash

# Network Analyze Tool Setup Script
# 需要以root用户执行
#
# 功能说明:
# 1. 换源
# 2. 安装Docker和容器运行时
# 3. 配置Docker使用crun运行时
# 4. 安装containerlab和相关工具
# 5. 克隆实验项目
# 6. 生成拓扑
# 7. 部署和测试网络

set -e  # 遇到错误时退出

# ============================================================================
# 1. 配置变量
# ============================================================================
SOFT_SOURCE="mirrors.pku.edu.cn"

# ============================================================================
# 2. 换源配置
# ============================================================================
echo "正在配置软件源..."
bash <(curl -sSL https://linuxmirrors.cn/main.sh) \
  --source $SOFT_SOURCE \
  --protocol http \
  --use-intranet-source false \
  --install-epel true \
  --backup true \
  --upgrade-software false \
  --clean-cache true \
  --ignore-backup-tips

# ============================================================================
# 3. Docker安装和配置
# ============================================================================
echo "正在安装Docker..."
bash <(curl -sSL https://linuxmirrors.cn/docker.sh) \
    --source $SOFT_SOURCE/docker-ce \
    --install-latest true --source-registry registry.cn-beijing.aliyuncs.com \
      --protocol http

echo "正在配置Docker运行时为crun..."
crun_path=$(which crun)
cat <<'EOF' | sudo tee /etc/docker/daemon.json
{
  "default-runtime": "crun",
  "runtimes": {
    "crun": {
      "path": "/usr/bin/crun"
    }
  }
}
EOF

sudo systemctl restart docker

# ============================================================================
# 4. 下载必要文件
# ============================================================================
echo "正在下载必要文件..."
wget https://xget.xi-xu.me/gh/srl-labs/containerlab/releases/download/v0.69.3/containerlab_0.69.3_linux_amd64.rpm
wget https://gitee.com/RubyMetric/chsrc/releases/download/v0.2.2/chsrc_latest-1_amd64.deb
wget https://cnb.cool/jmncnic/utils/-/releases/download/v1/crun-1.23.1-linux-amd64

# ============================================================================
# 5. 安装系统包
# ============================================================================
echo "正在安装系统包..."
# RedHat/CentOS/Fedora
sudo dnf install fish uv crun jq -y

# Debian/Ubuntu (备用)
sudo apt install -y fish crun jq

# ============================================================================
# 6. 用户权限配置
# ============================================================================
echo "正在配置用户权限..."
sudo usermod -aG clab_admins $USER && newgrp clab_admins

# ============================================================================
# 7. 克隆项目和初始化
# ============================================================================
echo "正在克隆项目..."
git clone https://xget.xi-xu.me/gh/chocolatedesue/network-analyze-tool.git --depth=1

echo "正在初始化项目..."
cd network-analyze-tool && uv sync && bash experiment_utils/setup/tn2.sh

# ============================================================================
# 8. 生成网络拓扑
# ============================================================================
echo "正在生成网络拓扑..."
uv run -m topo_gen torus 20 --dummy-gen ospf6d --yes --disable-logging
uv run -m topo_gen torus 25 --dummy-gen ospf6d --yes --disable-logging
uv run -m topo_gen torus 30 --dummy-gen ospf6d --yes --disable-logging

# ============================================================================
# 9. 部署容器实验室
# ============================================================================
echo "正在部署容器实验室..."
time clab deploy -t ospfv3_torus20x20/ --reconfigure --runtime podman
time clab deploy -t ospfv3_torus25x25/ --reconfigure --runtime podman

# ============================================================================
# 10. 批量执行配置重载
# ============================================================================
echo "正在执行批量配置重载..."
uv run experiment_utils/execute_in_batches.py clab-ospfv3-torus20x20 \
"/usr/lib/frr/frr-reload.py  --reload --daemon ospf6d /etc/frr/ospf6d-bak.conf" \
-r podman --percent 25 --interval 10 --detach --yes

uv run experiment_utils/execute_in_batches.py clab-ospfv3-torus25x25 \
"/usr/lib/frr/frr-reload.py  --reload --daemon ospf6d /etc/frr/ospf6d-bak.conf" \
-r podman --percent 25 --interval 10 --detach --yes

# ============================================================================
# 11. 网络连通性测试
# ============================================================================
echo "正在进行网络连通性测试..."
# 20x20拓扑测试
sudo podman exec -it clab-ospfv3-torus20x20-router_03_02 \
ping 2001:db8:1000:0:3:2:0:1

sudo podman exec -it clab-ospfv3-torus20x20-router_19_19 \
ping 2001:db8:1000:0:3:2:0:1

# 25x25拓扑测试
sudo podman exec -it clab-ospfv3-torus25x25-router_03_02 \
ping 2001:db8:1000:0:3:2:0:1

sudo podman exec -it clab-ospfv3-torus25x25-router_24_24 \
ping 2001:db8:1000:0:3:2:0:1

# ============================================================================
# 12. 清理和优化
# ============================================================================
echo "正在清理资源..."
clab destroy -t ospfv3_torus25x25

# 设置CPU亲和性
taskset -cp 1-15 $$

echo "脚本执行完成!"

