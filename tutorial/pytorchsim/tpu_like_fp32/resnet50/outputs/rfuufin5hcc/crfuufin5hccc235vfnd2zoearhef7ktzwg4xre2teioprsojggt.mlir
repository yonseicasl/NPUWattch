#map0 = affine_map<(index0, index1) -> (index1 + 196 * index0)>
memref.global @buf0_spad : memref<256x196xf32, 1>
#map1 = affine_map<(index0, index1) -> (index0 + 256 * index1)>
func.func @kernel(%in_ptr0: memref<50176xf32>,
                       %out_ptr0: memref<50176xf32>)
{
    %const0 = arith.constant 0 : index
    %const1 = arith.constant 4 : index
    %const2 = arith.constant 2 : index
    %const3 = arith.constant 3 : index
    %alloc0 = memref.alloc() : memref<1xi32> // 0
    %alloc1 = memref.alloc() : memref<1xi32> // 1
    %spad0 = memref.get_global @buf0_spad : memref<256x196xf32, 1>
    affine.for %index0 = 0 to 256 step 256
    {
        affine.for %index1 = 0 to 196 step 196
        {
            %apply0 = affine.apply #map0(%index0, %index1) // // store_reduction=False
            %apply1 = affine.apply #map1(%index0, %index1) // // store_reduction=False
            memref.dma_start %in_ptr0[%apply0], %spad0[%const0,%const0], %const2, %alloc0[%const0], %const0, %const1 : memref<50176xf32>, memref<256x196xf32, 1>, memref<1xi32> {dram_stride = [196, 1], sram_stride = [196, 1], padding = 0}
            affine.for %compute_idx = 0 to 784 step 16
            {
                %tmp1 = affine.vector_load %spad0[%const0,%compute_idx] : memref<256x196xf32, 1>, vector<16xf32>
            } {inner_loop=false}
            memref.dma_start %spad0[%const0,%const0], %out_ptr0[%apply1], %const3, %alloc1[%const0], %const0, %const1 : memref<256x196xf32, 1>, memref<50176xf32>, memref<1xi32> {dram_stride = [1, 256], sram_stride = [196, 1], padding = 0}
        } {outer_loop=true}
    } {outer_loop=true}
    return
}
