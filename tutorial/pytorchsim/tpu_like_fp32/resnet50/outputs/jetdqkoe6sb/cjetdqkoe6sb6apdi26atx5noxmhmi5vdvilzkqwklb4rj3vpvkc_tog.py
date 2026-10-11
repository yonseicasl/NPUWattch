graph = {
0 : {
	"node_id": 0,
	"node_name": "root",
	"node_type": 0,
	"parents": [],
	"children": [1]
}
,1 : {
	"node_id": 1,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [0],
	"children": [2],
	"loop_index": "loop_arg000",
	"loop_start": 0,
	"loop_end": 512,
	"loop_step": 512,
	"loop_type": "outer_loop"
}
,2 : {
	"node_id": 2,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [1],
	"children": [3],
	"loop_index": "loop_arg001",
	"loop_start": 0,
	"loop_end": 7,
	"loop_step": 7,
	"loop_type": "outer_loop"
}
,3 : {
	"node_id": 3,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [2],
	"children": [4,5,28],
	"loop_index": "loop_arg002",
	"loop_start": 0,
	"loop_end": 8,
	"loop_step": 8,
	"loop_type": "outer_loop"
}
,4 : {
	"node_id": 4,
	"node_name": "ComputeNode",
	"node_type": 1,
	"parents": [3],
	"children": [],
	"compute_cycle": 0,
	"compute_type": 0
}
,5 : {
	"node_id": 5,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [3],
	"children": [6],
	"loop_index": "loop_arg003",
	"loop_start": 0,
	"loop_end": 3,
	"loop_step": 1,
	"loop_type": "accumulation_loop"
}
,6 : {
	"node_id": 6,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [5],
	"children": [7],
	"loop_index": "loop_arg004",
	"loop_start": 0,
	"loop_end": 3,
	"loop_step": 1,
	"loop_type": "accumulation_loop"
}
,7 : {
	"node_id": 7,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [6],
	"children": [8,17],
	"loop_index": "loop_arg005",
	"loop_start": 0,
	"loop_end": 512,
	"loop_step": 512,
	"loop_type": "accumulation_loop"
}
,8 : {
	"node_id": 8,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [7],
	"children": [9],
	"loop_index": "loop_arg006",
	"loop_start": 0,
	"loop_end": 1,
	"loop_step": 1,
	"loop_type": "inner_loop"
}
,9 : {
	"node_id": 9,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [8],
	"children": [10],
	"loop_index": "loop_arg007",
	"loop_start": 0,
	"loop_end": 7,
	"loop_step": 1,
	"loop_type": "inner_loop"
}
,10 : {
	"node_id": 10,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [9],
	"children": [11],
	"loop_index": "loop_arg008",
	"loop_start": 0,
	"loop_end": 1,
	"loop_step": 1,
	"loop_type": "inner_loop"
}
,11 : {
	"node_id": 11,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [10],
	"children": [12],
	"loop_index": "loop_arg009",
	"loop_start": 0,
	"loop_end": 1,
	"loop_step": 1,
	"loop_type": "inner_loop"
}
,12 : {
	"node_id": 12,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [11],
	"children": [13],
	"loop_index": "loop_arg010",
	"loop_start": 0,
	"loop_end": 1,
	"loop_step": 1,
	"loop_type": "inner_loop"
}
,13 : {
	"node_id": 13,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [12],
	"children": [14],
	"loop_index": "loop_arg011",
	"loop_start": 0,
	"loop_end": 1,
	"loop_step": 1,
	"loop_type": "inner_loop"
}
,14 : {
	"node_id": 14,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [13],
	"children": [15,16],
	"loop_index": "loop_arg012",
	"loop_start": 0,
	"loop_end": 4,
	"loop_step": 1,
	"loop_type": "inner_loop"
}
,15 : {
	"node_id": 15,
	"node_name": "DMANode",
	"node_type": 3,
	"parents": [14],
	"children": [],
	"is_write": 0,
	"is_async": 1,
	"base_address": "arg0",
	"indirect_mode": 0,
	"tile_size": [1,1,8,512],
	"tile_stride": [46080,5120,512,1],
	"tag_idx_list": ["loop_arg006","loop_arg007","loop_arg010","loop_arg011"],
	"tag_stride_list": [7,1,1,1],
	"loop_idx_list": ["c0","loop_arg001","loop_arg002","loop_arg003","loop_arg004","loop_arg005","loop_arg006","loop_arg007","loop_arg010","loop_arg011"],
	"loop_stride_list": [0,1,1,1,1,1,46080,5120,4096,512],
	"element_size": 32
}
,16 : {
	"node_id": 16,
	"node_name": "DMANode",
	"node_type": 3,
	"parents": [14],
	"children": [],
	"is_write": 0,
	"is_async": 1,
	"base_address": "arg1",
	"indirect_mode": 0,
	"tile_size": [1,1,512,128],
	"tile_stride": [786432,262144,512,1],
	"tag_idx_list": ["loop_arg008","loop_arg009","loop_arg011","loop_arg012"],
	"tag_stride_list": [4,4,4,1],
	"loop_idx_list": ["loop_arg000","loop_arg003","loop_arg004","loop_arg005","loop_arg008","loop_arg009","loop_arg011","loop_arg012"],
	"loop_stride_list": [1,786432,262144,512,786432,262144,262144,128],
	"element_size": 32
}
,17 : {
	"node_id": 17,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [7],
	"children": [18],
	"loop_index": "loop_arg013",
	"loop_start": 0,
	"loop_end": 1,
	"loop_step": 1,
	"loop_type": "inner_loop"
}
,18 : {
	"node_id": 18,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [17],
	"children": [19],
	"loop_index": "loop_arg014",
	"loop_start": 0,
	"loop_end": 1,
	"loop_step": 1,
	"loop_type": "inner_loop"
}
,19 : {
	"node_id": 19,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [18],
	"children": [20],
	"loop_index": "loop_arg015",
	"loop_start": 0,
	"loop_end": 4,
	"loop_step": 1,
	"loop_type": "inner_loop"
}
,20 : {
	"node_id": 20,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [19],
	"children": [21,23,24],
	"loop_index": "loop_arg016",
	"loop_start": 0,
	"loop_end": 4,
	"loop_step": 1,
	"loop_type": "inner_loop"
}
,21 : {
	"node_id": 21,
	"node_name": "DMAWaitNode",
	"node_type": 4,
	"parents": [20],
	"children": [],
	"base_address": "arg1",
	"tag_idx_list": ["loop_arg003","loop_arg004","loop_arg005","loop_arg013","loop_arg014","loop_arg015","0"],
	"tag_stride_list": [-1,-1,-1,4,4,1,4],
	"tag_divider_list": [1,1,1,1,1,1,4]}
,23 : {
	"node_id": 23,
	"node_name": "ComputeNode",
	"node_type": 1,
	"parents": [20],
	"children": [],
	"compute_cycle": 0,
	"compute_type": 2
}
,24 : {
	"node_id": 24,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [20],
	"children": [25],
	"loop_index": "loop_arg017",
	"loop_start": 0,
	"loop_end": 7,
	"loop_step": 1,
	"loop_type": "inner_loop"
}
,25 : {
	"node_id": 25,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [24],
	"children": [26,27],
	"loop_index": "loop_arg018",
	"loop_start": 0,
	"loop_end": 1,
	"loop_step": 1,
	"loop_type": "inner_loop"
}
,26 : {
	"node_id": 26,
	"node_name": "DMAWaitNode",
	"node_type": 4,
	"parents": [25],
	"children": [],
	"base_address": "arg0",
	"tag_idx_list": ["loop_arg003","loop_arg004","loop_arg005","loop_arg017","loop_arg018","0","0"],
	"tag_stride_list": [-1,-1,-1,1,1,1,1],
	"tag_divider_list": [1,1,1,1,1,1,1]}
,27 : {
	"node_id": 27,
	"node_name": "ComputeNode",
	"node_type": 1,
	"parents": [25],
	"children": [],
	"compute_cycle": 0,
	"compute_type": 1
}
,28 : {
	"node_id": 28,
	"node_name": "DMANode",
	"node_type": 3,
	"parents": [3],
	"children": [],
	"is_write": 1,
	"is_async": 0,
	"base_address": "arg2",
	"indirect_mode": 0,
	"tile_size": [1,512,7,8],
	"tile_stride": [0,56,8,1],
	"tag_idx_list": ["0"],
	"tag_stride_list": [1],
	"loop_idx_list": ["c0","loop_arg000","loop_arg001","loop_arg002"],
	"loop_stride_list": [0,56,8,1],
	"element_size": 32
}
,}