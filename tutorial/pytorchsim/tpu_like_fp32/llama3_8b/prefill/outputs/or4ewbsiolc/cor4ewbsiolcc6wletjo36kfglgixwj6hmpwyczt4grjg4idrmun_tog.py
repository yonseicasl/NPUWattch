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
	"children": [3,4,5,6,7],
	"loop_index": "loop_arg001",
	"loop_start": 0,
	"loop_end": 4096,
	"loop_step": 1024,
	"loop_type": "outer_loop"
}
,3 : {
	"node_id": 3,
	"node_name": "DMANode",
	"node_type": 3,
	"parents": [2],
	"children": [],
	"is_write": 0,
	"is_async": 0,
	"base_address": "arg0",
	"indirect_mode": 0,
	"tile_size": [512,1024],
	"tile_stride": [4096,1],
	"tag_idx_list": ["0"],
	"tag_stride_list": [1],
	"loop_idx_list": ["loop_arg000","loop_arg001"],
	"loop_stride_list": [4096,1],
	"element_size": 32
}
,4 : {
	"node_id": 4,
	"node_name": "DMANode",
	"node_type": 3,
	"parents": [2],
	"children": [],
	"is_write": 0,
	"is_async": 0,
	"base_address": "arg1",
	"indirect_mode": 0,
	"tile_size": [512,1024],
	"tile_stride": [1,0],
	"tag_idx_list": ["0"],
	"tag_stride_list": [1],
	"loop_idx_list": ["loop_arg000"],
	"loop_stride_list": [1],
	"element_size": 32
}
,5 : {
	"node_id": 5,
	"node_name": "DMANode",
	"node_type": 3,
	"parents": [2],
	"children": [],
	"is_write": 0,
	"is_async": 0,
	"base_address": "arg2",
	"indirect_mode": 0,
	"tile_size": [512,1024],
	"tile_stride": [0,1],
	"tag_idx_list": ["0"],
	"tag_stride_list": [1],
	"loop_idx_list": ["loop_arg001"],
	"loop_stride_list": [1],
	"element_size": 32
}
,6 : {
	"node_id": 6,
	"node_name": "ComputeNode",
	"node_type": 1,
	"parents": [2],
	"children": [],
	"compute_cycle": 0,
	"compute_type": 0
}
,7 : {
	"node_id": 7,
	"node_name": "DMANode",
	"node_type": 3,
	"parents": [2],
	"children": [],
	"is_write": 1,
	"is_async": 0,
	"base_address": "arg3",
	"indirect_mode": 0,
	"tile_size": [512,1024],
	"tile_stride": [4096,1],
	"tag_idx_list": ["0"],
	"tag_stride_list": [1],
	"loop_idx_list": ["loop_arg000","loop_arg001"],
	"loop_stride_list": [4096,1],
	"element_size": 32
}
,}