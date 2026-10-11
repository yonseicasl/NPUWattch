#map0 = affine_map<(index0, index1, index2) -> (index2 + 9 * index1 + 4608 * index0)>
memref.global @buf0_spad : memref<32x512x10xf32, 1>
#map1 = affine_map<(index0, index1, index2) -> (index1 + 512 * index2 + 4608 * index0)>
func.func @kernel(%in_ptr0: memref<2359296xf32>,
                       %out_ptr0: memref<2359296xf32>)
{
    %const0 = arith.constant 0 : index
    %const1 = arith.constant 1 : index
    %const2 = arith.constant 8 : index
    %const3 = arith.constant 2 : index
    %const4 = arith.constant 3 : index
    %alloc0 = memref.alloc() : memref<1xi32> // 0
    %alloc1 = memref.alloc() : memref<1xi32> // 1
    %spad0 = memref.get_global @buf0_spad : memref<32x512x10xf32, 1>
    affine.for %index0 = 0 to 512 step 32
    {
        affine.for %index1 = 0 to 512 step 512
        {
            affine.for %index2 = 0 to 9 step 10
            {
                %apply0 = affine.apply #map0(%index0, %index1, %index2) // // store_reduction=False
                %apply1 = affine.apply #map1(%index0, %index1, %index2) // // store_reduction=False
                memref.dma_start %in_ptr0[%apply0], %spad0[%const0,%const0,%const0], %const3, %alloc0[%const0], %const1, %const2 : memref<2359296xf32>, memref<32x512x10xf32, 1>, memref<1xi32> {dram_stride = [4608, 9, 1], sram_stride = [5120, 10, 1], padding = 0}
                affine.for %compute_idx = 0 to 2560 step 16
                {
                    %tmp1 = affine.vector_load %spad0[%const0,%const0,%compute_idx] : memref<32x512x10xf32, 1>, vector<16xf32>
                } {inner_loop=false}
                memref.dma_start %spad0[%const0,%const0,%const0], %out_ptr0[%apply1], %const4, %alloc1[%const0], %const1, %const2 : memref<32x512x10xf32, 1>, memref<2359296xf32>, memref<1xi32> {dram_stride = [4608, 1, 512], sram_stride = [5120, 10, 1], padding = 0}
            } {outer_loop=true}
        } {outer_loop=true}
    } {outer_loop=true}
    return
}
