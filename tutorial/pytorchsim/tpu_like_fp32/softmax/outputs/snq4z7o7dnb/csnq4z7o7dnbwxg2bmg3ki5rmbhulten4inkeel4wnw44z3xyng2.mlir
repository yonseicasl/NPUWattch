#map0 = affine_map<(index0, index1) -> (index1 + 1024 * index0)>
memref.global @buf0_spad : memref<1024x512xf32, 1>
memref.global @buf1_spad : memref<1024x512xf32, 1>
memref.global @buf2_spad : memref<1024x512xf32, 1>
memref.global @buf3_spad : memref<1024x512xf32, 1>
func.func @kernel(%in_ptr0: memref<1048576xf32>,
                       %in_ptr1: memref<1024xf32>,
                       %in_ptr2: memref<1024xf32>,
                       %out_ptr0: memref<1048576xf32>)
{
    %const0 = arith.constant 0 : index
    %const1 = arith.constant 4 : index
    %const2 = arith.constant 2 : index
    %const3 = arith.constant 3 : index
    %alloc0 = memref.alloc() : memref<1xi32> // 0
    %alloc1 = memref.alloc() : memref<1xi32> // 1
    %alloc2 = memref.alloc() : memref<1xi32> // 2
    %alloc3 = memref.alloc() : memref<1xi32> // 3
    %spad0 = memref.get_global @buf0_spad : memref<1024x512xf32, 1>
    %spad1 = memref.get_global @buf1_spad : memref<1024x512xf32, 1>
    %spad2 = memref.get_global @buf2_spad : memref<1024x512xf32, 1>
    %spad3 = memref.get_global @buf3_spad : memref<1024x512xf32, 1>
    affine.for %index0 = 0 to 1024 step 1024
    {
        affine.for %index1 = 0 to 1024 step 512
        {
            %apply0 = affine.apply #map0(%index0, %index1) // // store_reduction=False
            memref.dma_start %in_ptr0[%apply0], %spad0[%const0,%const0], %const2, %alloc0[%const0], %const0, %const1 : memref<1048576xf32>, memref<1024x512xf32, 1>, memref<1xi32> {dram_stride = [1024, 1], sram_stride = [512, 1], padding = 0}
            memref.dma_start %in_ptr1[%index0], %spad1[%const0,%const0], %const2, %alloc1[%const0], %const0, %const1 : memref<1024xf32>, memref<1024x512xf32, 1>, memref<1xi32> {dram_stride = [1, 0], sram_stride = [512, 1], padding = 0}
            memref.dma_start %in_ptr2[%index0], %spad2[%const0,%const0], %const2, %alloc2[%const0], %const0, %const1 : memref<1024xf32>, memref<1024x512xf32, 1>, memref<1xi32> {dram_stride = [1, 0], sram_stride = [512, 1], padding = 0}
            affine.for %compute_idx = 0 to 4096 step 16
            {
                %tmp1 = affine.vector_load %spad0[%const0,%compute_idx] : memref<1024x512xf32, 1>, vector<16xf32>
                %tmp3 = affine.vector_load %spad1[%const0,%compute_idx] : memref<1024x512xf32, 1>, vector<16xf32>
                %tmp7 = affine.vector_load %spad2[%const0,%compute_idx] : memref<1024x512xf32, 1>, vector<16xf32>
                %tmp4 = arith.subf %tmp1, %tmp3 : vector<16xf32>
                %tmp5 = math.exp %tmp4 : vector<16xf32>
                %tmp8 = arith.divf %tmp5, %tmp7 : vector<16xf32>
                affine.vector_store %tmp8, %spad3[%const0,%compute_idx] : memref<1024x512xf32, 1>, vector<16xf32>
            } {inner_loop=false}
            memref.dma_start %spad3[%const0,%const0], %out_ptr0[%apply0], %const3, %alloc3[%const0], %const0, %const1 : memref<1024x512xf32, 1>, memref<1048576xf32>, memref<1xi32> {dram_stride = [1024, 1], sram_stride = [512, 1], padding = 0}
        } {outer_loop=true}
    } {outer_loop=true}
    return
}
