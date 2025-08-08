import networkx as nx
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from pathlib import Path

# 1. 定义特殊节点
source_node = (1, 4)
dest_node = (4, 1)

# 2. 初始化图和位置
G = nx.grid_2d_graph(6, 6)
pos = {(x, y): (y, -x) for x, y in G.nodes()}

plt.style.use('seaborn-v0_8-whitegrid')
# 使用适合6x6网格的画布尺寸
fig, ax = plt.subplots(figsize=(8, 6)) 
ax.set_title(
    "Domain Division Sample (6x6)",
    fontsize=16,
    fontweight='bold',
)

# 3. 定义区域和连接
subregion_definitions = [
    {'start': (0, 0), 'color': '#E69F00'},
    {'start': (0, 3), 'color': '#56B4E9'},
    {'start': (3, 0), 'color': '#009E73'},
    {'start': (3, 3), 'color': '#CC79A7'},
]
internal_bridge_edges = [
    ((1, 2), (1, 3)), ((4, 2), (4, 3)),
    ((2, 1), (3, 1)), ((2, 4), (3, 4)),
]
torus_bridge_edges = [
    ((0, 1), (5, 1)), ((0, 4), (5, 4)),
    ((1, 0), (1, 5)), ((4, 0), (4, 5)),
]
gateway_nodes = set(n for e in internal_bridge_edges + torus_bridge_edges for n in e)

# 4. 绘制每个子区域的基础节点和边
for region in subregion_definitions:
    start_x, start_y = region['start']
    color = region['color']
    
    region_nodes = [(x, y) for x in range(start_x, start_x+3) for y in range(start_y, start_y+3)]
    
    # 过滤掉后面要特殊绘制的源点和目的点
    base_nodes = [n for n in region_nodes if n not in [source_node, dest_node]]
    internal_base_nodes = [n for n in base_nodes if n not in gateway_nodes]
    gateway_base_nodes = [n for n in base_nodes if n in gateway_nodes]
    
    subgraph = G.subgraph(region_nodes)
    nx.draw_networkx_edges(subgraph, pos, ax=ax, edge_color=color, width=2.0)
    nx.draw_networkx_nodes(G, pos, ax=ax, nodelist=internal_base_nodes, node_color=color, node_shape='o', node_size=180)
    nx.draw_networkx_nodes(G, pos, ax=ax, nodelist=gateway_base_nodes, node_color=color, node_shape='s', node_size=300, edgecolors='black', linewidths=2.0)

# 5. 绘制连接线
nx.draw_networkx_edges(G, pos, ax=ax, edgelist=internal_bridge_edges, edge_color='black', width=2.5, style='dashed')
for u, v in torus_bridge_edges:
    pos_u, pos_v = pos[u], pos[v]
    if u[0] == v[0]:
        stub_u, stub_v = (pos_u[0] - 0.4, pos_u[1]), (pos_v[0] + 0.4, pos_v[1])
    else:
        stub_u, stub_v = (pos_u[0], pos_u[1] + 0.4), (pos_v[0], pos_v[1] - 0.4)
    ax.plot([pos_u[0], stub_u[0]], [pos_u[1], stub_u[1]], color='#D55E00', lw=2.0, linestyle='--')
    ax.plot([pos_v[0], stub_v[0]], [pos_v[1], stub_v[1]], color='#D55E00', lw=2.0, linestyle='--')

# 6. 特殊标注源点 (Source) 用三角形，目的点 (Destination) 用星形
nx.draw_networkx_nodes(
    G, pos, ax=ax, nodelist=[source_node],
    node_shape='^',
    node_color='#FF00FF',  # 源点：洋红色
    node_size=400,
    edgecolors='black', linewidths=2.0
)
nx.draw_networkx_nodes(
    G, pos, ax=ax, nodelist=[dest_node],
    node_shape='*',
    node_color='#E69F00',  # 目的点：金黄色
    node_size=400,
    edgecolors='black', linewidths=2.0
)

# 7. 绘制图例
legend_elements = [
    Line2D([0], [0], marker='o', color='w', label='Internal Node', markerfacecolor='gray', markersize=10),
    Line2D([0], [0], marker='s', color='w', label='Gateway Node', markerfacecolor='gray', markeredgecolor='black', markersize=10, mew=1.5),
    Line2D([0], [0], marker='^', color='w', label='Source Node', markerfacecolor='#FF00FF', markeredgecolor='black', markersize=10, mew=1.5),
    Line2D([0], [0], marker='*', color='w', label='Destination Node', markerfacecolor='#E69F00', markeredgecolor='black', markersize=12, mew=1.5),
    Line2D([0], [0], color='black', lw=2.5, linestyle='--', label='Neighbor Connection'),
    Line2D([0], [0], color='#D55E00', lw=2.0, linestyle='--', label='Torus Connection')
]
legend = ax.legend(
    handles=legend_elements,
    loc='upper right',
    fontsize=10,
    title='Legend',
    title_fontsize='12',
    frameon=True, fancybox=True, framealpha=0.9,
    facecolor='white', edgecolor='gray', shadow=True
)

# 8. 美化并显示
ax.set_aspect('equal', adjustable='box')
ax.margins(0.1)
plt.box(False)
ax.set_xticks([])
ax.set_yticks([])
output_path = Path('domainDiv/draw/res/dm6_6_sample.png')
output_path.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(output_path, bbox_inches='tight', dpi=300)
plt.show()
