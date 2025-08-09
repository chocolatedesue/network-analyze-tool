
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


sudo dnf config-manager -y --add-repo "https://netdevops.fury.site/yum/" && \
echo "gpgcheck=0" | sudo tee -a /etc/yum.repos.d/netdevops.fury.site_yum_.repo

sudo dnf install containerlab fish uv crun jq -y

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

git clone https://xget.xi-xu.me/gh/chocolatedesue/network-analyze-tool.git --depth=1

cd network-analyze-tool && uv sync && bash experiment_utils/setup/tn2.sh

