#map0 = affine_map<(index0, index1, index2) -> (index2 + 49 * index1 + 147 * index0)>
memref.global @buf0_spad : memref<32x3x52xf32, 1>
#map1 = affine_map<(index0, index1, index2) -> (index1 + 3 * index2 + 147 * index0)>
func.func @kernel(%in_ptr0: memref<9408xf32>,
                       %out_ptr0: memref<9408xf32>)
{
    %const0 = arith.constant 0 : index
    %const1 = arith.constant 2 : index
    %const2 = arith.constant 4 : index
    %const3 = arith.constant 3 : index
    %alloc0 = memref.alloc() : memref<1xi32> // 0
    %alloc1 = memref.alloc() : memref<1xi32> // 1
    %spad0 = memref.get_global @buf0_spad : memref<32x3x52xf32, 1>
    affine.for %index0 = 0 to 64 step 32
    {
        affine.for %index1 = 0 to 3 step 3
        {
            affine.for %index2 = 0 to 49 step 52
            {
                %apply0 = affine.apply #map0(%index0, %index1, %index2) // // store_reduction=False
                %apply1 = affine.apply #map1(%index0, %index1, %index2) // // store_reduction=False
                memref.dma_start %in_ptr0[%apply0], %spad0[%const0,%const0,%const0], %const1, %alloc0[%const0], %const1, %const2 : memref<9408xf32>, memref<32x3x52xf32, 1>, memref<1xi32> {dram_stride = [147, 49, 1], sram_stride = [156, 52, 1], padding = 0}
                affine.for %compute_idx = 0 to 384 step 8
                {
                    %tmp1 = affine.vector_load %spad0[%const0,%const0,%compute_idx] : memref<32x3x52xf32, 1>, vector<8xf32>
                } {inner_loop=false}
                memref.dma_start %spad0[%const0,%const0,%const0], %out_ptr0[%apply1], %const3, %alloc1[%const0], %const1, %const2 : memref<32x3x52xf32, 1>, memref<9408xf32>, memref<1xi32> {dram_stride = [147, 1, 3], sram_stride = [156, 52, 1], padding = 0}
            } {outer_loop=true}
        } {outer_loop=true}
    } {outer_loop=true}
    return
}
