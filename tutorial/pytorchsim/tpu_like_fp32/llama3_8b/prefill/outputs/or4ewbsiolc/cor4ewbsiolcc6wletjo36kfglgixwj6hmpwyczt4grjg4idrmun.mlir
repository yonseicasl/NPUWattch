#map0 = affine_map<(index0, index1) -> (index1 + 4096 * index0)>
memref.global @buf0_spad : memref<512x1024xf32, 1>
memref.global @buf1_spad : memref<512x1024xf32, 1>
memref.global @buf2_spad : memref<512x1024xf32, 1>
memref.global @buf3_spad : memref<512x1024xf32, 1>
func.func @kernel(%in_ptr0: memref<2097152xf32>,
                       %in_ptr1: memref<512xf32>,
                       %in_ptr2: memref<4096xf32>,
                       %out_ptr0: memref<2097152xf32>)
{
    %const0 = arith.constant 0 : index
    %const1 = arith.constant 1 : index
    %const2 = arith.constant 4 : index
    %const3 = arith.constant 2 : index
    %const4 = arith.constant 3 : index
    %alloc0 = memref.alloc() : memref<1xi32> // 0
    %alloc1 = memref.alloc() : memref<1xi32> // 1
    %alloc2 = memref.alloc() : memref<1xi32> // 2
    %alloc3 = memref.alloc() : memref<1xi32> // 3
    %spad0 = memref.get_global @buf0_spad : memref<512x1024xf32, 1>
    %spad1 = memref.get_global @buf1_spad : memref<512x1024xf32, 1>
    %spad2 = memref.get_global @buf2_spad : memref<512x1024xf32, 1>
    %spad3 = memref.get_global @buf3_spad : memref<512x1024xf32, 1>
    affine.for %index0 = 0 to 512 step 512
    {
        affine.for %index1 = 0 to 4096 step 1024
        {
            %apply0 = affine.apply #map0(%index0, %index1) // // store_reduction=False
            memref.dma_start %in_ptr0[%apply0], %spad0[%const0,%const0], %const3, %alloc0[%const0], %const1, %const2 : memref<2097152xf32>, memref<512x1024xf32, 1>, memref<1xi32> {dram_stride = [4096, 1], sram_stride = [1024, 1], padding = 0}
            memref.dma_start %in_ptr1[%index0], %spad1[%const0,%const0], %const3, %alloc1[%const0], %const1, %const2 : memref<512xf32>, memref<512x1024xf32, 1>, memref<1xi32> {dram_stride = [1, 0], sram_stride = [1024, 1], padding = 0}
            memref.dma_start %in_ptr2[%index1], %spad2[%const0,%const0], %const3, %alloc2[%const0], %const1, %const2 : memref<4096xf32>, memref<512x1024xf32, 1>, memref<1xi32> {dram_stride = [0, 1], sram_stride = [1024, 1], padding = 0}
            affine.for %compute_idx = 0 to 4096 step 16
            {
                %tmp1 = affine.vector_load %spad0[%const0,%compute_idx] : memref<512x1024xf32, 1>, vector<16xf32>
                %tmp3 = affine.vector_load %spad1[%const0,%compute_idx] : memref<512x1024xf32, 1>, vector<16xf32>
                %tmp13 = affine.vector_load %spad2[%const0,%compute_idx] : memref<512x1024xf32, 1>, vector<16xf32>
                %tmp4 = arith.constant 4096.00000000000000000000 : f32
                %tmp5 = vector.broadcast %tmp4 : f32 to vector<16xf32>
                %tmp6 = arith.divf %tmp3, %tmp5 : vector<16xf32>
                %tmp7 = arith.constant 0.00001000000000000000 : f32
                %tmp8 = vector.broadcast %tmp7 : f32 to vector<16xf32>
                %tmp9 = arith.addf %tmp6, %tmp8 : vector<16xf32>
                %tmp10 = math.rsqrt %tmp9 : vector<16xf32>
                %tmp11 = arith.mulf %tmp1, %tmp10 : vector<16xf32>
                %tmp14 = arith.mulf %tmp11, %tmp13 : vector<16xf32>
                affine.vector_store %tmp14, %spad3[%const0,%compute_idx] : memref<512x1024xf32, 1>, vector<16xf32>
            } {inner_loop=false}
            memref.dma_start %spad3[%const0,%const0], %out_ptr0[%apply0], %const4, %alloc3[%const0], %const1, %const2 : memref<512x1024xf32, 1>, memref<2097152xf32>, memref<1xi32> {dram_stride = [4096, 1], sram_stride = [1024, 1], padding = 0}
        } {outer_loop=true}
    } {outer_loop=true}
    return
}
