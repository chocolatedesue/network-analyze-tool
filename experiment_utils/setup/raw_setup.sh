
# 1. 换源
# 2. 构建 crun 和 安装docker
# 3. 将 docker 默认 runtime 切换为 crun
# 4. 安装 containerlab mise 
# 5. clone 实验项目
# 需要以root用户执行


#  mirrors.pku.edu.cn
SOFT_SOURCE="mirrors.pku.edu.cn"    



bash <(curl -sSL https://linuxmirrors.cn/main.sh) \
  --source $SOFT_SOURCE \
  --protocol http \
  --use-intranet-source false \
  --install-epel true \
  --backup true \
  --upgrade-software false \
  --clean-cache true \
  --ignore-backup-tips


bash <(curl -sSL https://linuxmirrors.cn/docker.sh) \
    --source $SOFT_SOURCE/docker-ce \
    --install-latest true --source-registry registry.cn-beijing.aliyuncs.com \
      --protocol http 


# sudo dnf config-manager -y --add-repo "https://netdevops.fury.site/yum/" && \
# echo "gpgcheck=0" | sudo tee -a /etc/yum.repos.d/netdevops.fury.site_yum_.repo

wget https://xget.xi-xu.me/gh/srl-labs/containerlab/releases/download/v0.69.3/containerlab_0.69.3_linux_amd64.rpm
wget https://gitee.com/RubyMetric/chsrc/releases/download/v0.2.2/chsrc_latest-1_amd64.deb
wget https://cnb.cool/jmncnic/utils/-/releases/download/v1/crun-1.23.1-linux-amd64
sudo dnf install fish uv crun jq -y

sudo apt install -y fish crun jq
# change docker default runtime to crun, edit /etc/docker/daemon.json

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


wget 

git clone https://xget.xi-xu.me/gh/chocolatedesue/network-analyze-tool.git --depth=1

cd network-analyze-tool && uv sync && bash experiment_utils/setup/tn2.sh


uv run -m topo_gen torus 25 --dummy-gen ospf6d --yes --disable-logging

uv run -m topo_gen torus 30 --dummy-gen ospf6d --yes --disable-logging


uv run -m topo_gen torus 20 --dummy-gen ospf6d --yes --disable-logging


time clab deploy -t ospfv3_torus25x25/ --reconfigure --runtime podman

sudo usermod -aG clab_admins $USER && newgrp clab_admins




uv run experiment_utils/execute_in_batches.py clab-ospfv3-torus25x25 \
"/usr/lib/frr/frr-reload.py  --reload --daemon ospf6d /etc/frr/ospf6d-bak.conf" \
-r podman --percent 25 --interval 10 --detach --yes

clab destroy -t ospfv3_torus25x25

sudo podman exec -it  clab-ospfv3-torus25x25-router_03_02 \
ping 2001:db8:1000:0:3:2:0:1

sudo podman exec -it  clab-ospfv3-torus25x25-router_24_24 \
ping 2001:db8:1000:0:3:2:0:1