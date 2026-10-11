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
	"children": [2,3,4],
	"loop_index": "loop_arg000",
	"loop_start": 0,
	"loop_end": 1048576,
	"loop_step": 8192,
	"loop_type": "outer_loop"
}
,2 : {
	"node_id": 2,
	"node_name": "DMANode",
	"node_type": 3,
	"parents": [1],
	"children": [],
	"is_write": 0,
	"is_async": 0,
	"base_address": "arg0",
	"indirect_mode": 0,
	"tile_size": [8192],
	"tile_stride": [1],
	"tag_idx_list": ["0"],
	"tag_stride_list": [1],
	"loop_idx_list": ["loop_arg000"],
	"loop_stride_list": [1],
	"element_size": 32
}
,3 : {
	"node_id": 3,
	"node_name": "ComputeNode",
	"node_type": 1,
	"parents": [1],
	"children": [],
	"compute_cycle": 0,
	"compute_type": 0
}
,4 : {
	"node_id": 4,
	"node_name": "DMANode",
	"node_type": 3,
	"parents": [1],
	"children": [],
	"is_write": 1,
	"is_async": 0,
	"base_address": "arg1",
	"indirect_mode": 0,
	"tile_size": [8192],
	"tile_stride": [1],
	"tag_idx_list": ["0"],
	"tag_stride_list": [1],
	"loop_idx_list": ["loop_arg000"],
	"loop_stride_list": [1],
	"element_size": 32
}
,}