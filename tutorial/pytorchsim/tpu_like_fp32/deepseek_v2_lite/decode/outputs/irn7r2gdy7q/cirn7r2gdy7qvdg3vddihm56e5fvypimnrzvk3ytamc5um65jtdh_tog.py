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
	"loop_end": 6,
	"loop_step": 1,
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
	"loop_end": 8,
	"loop_step": 8,
	"loop_type": "outer_loop"
}
,3 : {
	"node_id": 3,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [2],
	"children": [4,5,18],
	"loop_index": "loop_arg002",
	"loop_start": 0,
	"loop_end": 2048,
	"loop_step": 2048,
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
	"children": [6,12],
	"loop_index": "loop_arg003",
	"loop_start": 0,
	"loop_end": 1408,
	"loop_step": 128,
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
	"loop_end": 1,
	"loop_step": 1,
	"loop_type": "inner_loop"
}
,7 : {
	"node_id": 7,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [6],
	"children": [8],
	"loop_index": "loop_arg005",
	"loop_start": 0,
	"loop_end": 1,
	"loop_step": 1,
	"loop_type": "inner_loop"
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
	"children": [10,11],
	"loop_index": "loop_arg007",
	"loop_start": 0,
	"loop_end": 1,
	"loop_step": 1,
	"loop_type": "inner_loop"
}
,10 : {
	"node_id": 10,
	"node_name": "DMANode",
	"node_type": 3,
	"parents": [9],
	"children": [],
	"is_write": 0,
	"is_async": 1,
	"base_address": "arg0",
	"indirect_mode": 0,
	"tile_size": [1,8,128],
	"tile_stride": [1408,1408,1],
	"tag_idx_list": ["loop_arg004","loop_arg005","loop_arg006"],
	"tag_stride_list": [1,1,1],
	"loop_idx_list": ["loop_arg000","loop_arg001","loop_arg003","loop_arg004","loop_arg005","loop_arg006"],
	"loop_stride_list": [11264,1408,1,1408,11264,128],
	"element_size": 32
}
,11 : {
	"node_id": 11,
	"node_name": "DMANode",
	"node_type": 3,
	"parents": [9],
	"children": [],
	"is_write": 0,
	"is_async": 1,
	"base_address": "arg1",
	"indirect_mode": 0,
	"tile_size": [1,128,2048],
	"tile_stride": [2883584,2048,1],
	"tag_idx_list": ["loop_arg004","loop_arg006","loop_arg007"],
	"tag_stride_list": [1,1,1],
	"loop_idx_list": ["loop_arg000","loop_arg002","loop_arg003","loop_arg004","loop_arg006","loop_arg007"],
	"loop_stride_list": [2883584,1,2048,2883584,262144,2048],
	"element_size": 32
}
,12 : {
	"node_id": 12,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [5],
	"children": [13,15,16,17],
	"loop_index": "loop_arg008",
	"loop_start": 0,
	"loop_end": 16,
	"loop_step": 1,
	"loop_type": "inner_loop"
}
,13 : {
	"node_id": 13,
	"node_name": "DMAWaitNode",
	"node_type": 4,
	"parents": [12],
	"children": [],
	"base_address": "arg1",
	"tag_idx_list": ["loop_arg003","0","0"],
	"tag_stride_list": [-1,1,1],
	"tag_divider_list": [1,1,1]}
,15 : {
	"node_id": 15,
	"node_name": "ComputeNode",
	"node_type": 1,
	"parents": [12],
	"children": [],
	"compute_cycle": 0,
	"compute_type": 2
}
,16 : {
	"node_id": 16,
	"node_name": "DMAWaitNode",
	"node_type": 4,
	"parents": [12],
	"children": [],
	"base_address": "arg0",
	"tag_idx_list": ["loop_arg003","0","0"],
	"tag_stride_list": [-1,1,1],
	"tag_divider_list": [1,1,1]}
,17 : {
	"node_id": 17,
	"node_name": "ComputeNode",
	"node_type": 1,
	"parents": [12],
	"children": [],
	"compute_cycle": 0,
	"compute_type": 1
}
,18 : {
	"node_id": 18,
	"node_name": "DMANode",
	"node_type": 3,
	"parents": [3],
	"children": [],
	"is_write": 1,
	"is_async": 0,
	"base_address": "arg2",
	"indirect_mode": 0,
	"tile_size": [1,8,2048],
	"tile_stride": [2048,2048,1],
	"tag_idx_list": ["0"],
	"tag_stride_list": [1],
	"loop_idx_list": ["loop_arg000","loop_arg001","loop_arg002"],
	"loop_stride_list": [16384,2048,1],
	"element_size": 32
}
,}