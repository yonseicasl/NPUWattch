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
	"loop_end": 8,
	"loop_step": 8,
	"loop_type": "outer_loop"
}
,2 : {
	"node_id": 2,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [1],
	"children": [3,4,17],
	"loop_index": "loop_arg001",
	"loop_start": 0,
	"loop_end": 4096,
	"loop_step": 4096,
	"loop_type": "outer_loop"
}
,3 : {
	"node_id": 3,
	"node_name": "ComputeNode",
	"node_type": 1,
	"parents": [2],
	"children": [],
	"compute_cycle": 0,
	"compute_type": 0
}
,4 : {
	"node_id": 4,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [2],
	"children": [5,10],
	"loop_index": "loop_arg002",
	"loop_start": 0,
	"loop_end": 4096,
	"loop_step": 256,
	"loop_type": "accumulation_loop"
}
,5 : {
	"node_id": 5,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [4],
	"children": [6],
	"loop_index": "loop_arg003",
	"loop_start": 0,
	"loop_end": 1,
	"loop_step": 1,
	"loop_type": "inner_loop"
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
	"children": [8,9],
	"loop_index": "loop_arg005",
	"loop_start": 0,
	"loop_end": 1,
	"loop_step": 1,
	"loop_type": "inner_loop"
}
,8 : {
	"node_id": 8,
	"node_name": "DMANode",
	"node_type": 3,
	"parents": [7],
	"children": [],
	"is_write": 0,
	"is_async": 1,
	"base_address": "arg0",
	"indirect_mode": 0,
	"tile_size": [8,256],
	"tile_stride": [4096,1],
	"tag_idx_list": ["loop_arg003","loop_arg004"],
	"tag_stride_list": [1,1],
	"loop_idx_list": ["loop_arg000","loop_arg002","loop_arg003","loop_arg004"],
	"loop_stride_list": [4096,1,32768,256],
	"element_size": 32
}
,9 : {
	"node_id": 9,
	"node_name": "DMANode",
	"node_type": 3,
	"parents": [7],
	"children": [],
	"is_write": 0,
	"is_async": 1,
	"base_address": "arg1",
	"indirect_mode": 0,
	"tile_size": [256,4096],
	"tile_stride": [4096,1],
	"tag_idx_list": ["loop_arg004","loop_arg005"],
	"tag_stride_list": [1,1],
	"loop_idx_list": ["loop_arg001","loop_arg002","loop_arg004","loop_arg005"],
	"loop_stride_list": [1,4096,1048576,4096],
	"element_size": 32
}
,10 : {
	"node_id": 10,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [4],
	"children": [11],
	"loop_index": "loop_arg006",
	"loop_start": 0,
	"loop_end": 32,
	"loop_step": 1,
	"loop_type": "inner_loop"
}
,11 : {
	"node_id": 11,
	"node_name": "loopNode",
	"node_type": 2,
	"parents": [10],
	"children": [12,14,15,16],
	"loop_index": "loop_arg007",
	"loop_start": 0,
	"loop_end": 2,
	"loop_step": 1,
	"loop_type": "inner_loop"
}
,12 : {
	"node_id": 12,
	"node_name": "DMAWaitNode",
	"node_type": 4,
	"parents": [11],
	"children": [],
	"base_address": "arg1",
	"tag_idx_list": ["loop_arg002","0","0"],
	"tag_stride_list": [-1,1,2],
	"tag_divider_list": [1,1,2]}
,14 : {
	"node_id": 14,
	"node_name": "ComputeNode",
	"node_type": 1,
	"parents": [11],
	"children": [],
	"compute_cycle": 0,
	"compute_type": 2
}
,15 : {
	"node_id": 15,
	"node_name": "DMAWaitNode",
	"node_type": 4,
	"parents": [11],
	"children": [],
	"base_address": "arg0",
	"tag_idx_list": ["loop_arg002","0","0"],
	"tag_stride_list": [-1,1,1],
	"tag_divider_list": [1,1,1]}
,16 : {
	"node_id": 16,
	"node_name": "ComputeNode",
	"node_type": 1,
	"parents": [11],
	"children": [],
	"compute_cycle": 0,
	"compute_type": 1
}
,17 : {
	"node_id": 17,
	"node_name": "DMANode",
	"node_type": 3,
	"parents": [2],
	"children": [],
	"is_write": 1,
	"is_async": 0,
	"base_address": "arg2",
	"indirect_mode": 0,
	"tile_size": [8,4096],
	"tile_stride": [4096,1],
	"tag_idx_list": ["0"],
	"tag_stride_list": [1],
	"loop_idx_list": ["loop_arg000","loop_arg001"],
	"loop_stride_list": [4096,1],
	"element_size": 32
}
,}