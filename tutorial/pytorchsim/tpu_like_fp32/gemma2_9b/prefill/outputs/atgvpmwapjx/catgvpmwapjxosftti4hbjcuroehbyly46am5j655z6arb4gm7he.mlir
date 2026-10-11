#map0 = affine_map<(index0, index1) -> (index1 + 3584 * index0)>
memref.global @buf0_spad : memref<512x512xf32, 1>
memref.global @buf1_spad : memref<512xf32, 1>
func.func @kernel(%in_ptr0: memref<1835008xf32>,
                       %out_ptr0: memref<512xf32>)
{
    %const0 = arith.constant 0 : index
    %const1 = arith.constant 4 : index
    %const2 = arith.constant 2 : index
    %const3 = arith.constant 0.0 : f32
    %const4 = vector.broadcast %const3 : f32 to vector<16xf32>
    %const5 = arith.constant 3 : index
    %alloc0 = memref.alloc() : memref<1xi32> // 0
    %alloc1 = memref.alloc() : memref<1xi32> // 1
    %spad0 = memref.get_global @buf0_spad : memref<512x512xf32, 1>
    %spad1 = memref.get_global @buf1_spad : memref<512xf32, 1>
    affine.for %index0 = 0 to 512 step 512
    {
        %tmp_acc0 = affine.for %index1 = 0 to 3584 step 512 iter_args(%iter0 = %const4) -> (vector<16xf32>)
        {
            %apply0 = affine.apply #map0(%index0, %index1) // // store_reduction=False
            memref.dma_start %in_ptr0[%apply0], %spad0[%const0,%const0], %const2, %alloc0[%const0], %const0, %const1 : memref<1835008xf32>, memref<512x512xf32, 1>, memref<1xi32> {dram_stride = [3584, 1], sram_stride = [1, 512], padding = 0}
            %tmp_acc1 = affine.for %compute_idx = 0 to 2048 step 16 iter_args(%iter1 = %iter0) -> (vector<16xf32>)
            {
                %tmp1 = affine.vector_load %spad0[%const0,%compute_idx] : memref<512x512xf32, 1>, vector<16xf32>
                %tmp2 = arith.mulf %tmp1, %tmp1 : vector<16xf32>
                %tmp3 = arith.addf %tmp2, %iter1 : vector<16xf32>
                affine.yield %tmp3 : vector<16xf32>
            } {inner_loop=false}
            affine.yield %tmp_acc1 : vector<16xf32>
        } {accumulation_loop=true}
        %tmp4 = vector.broadcast %const3 : f32 to vector<4xf32>
        %tmp5 = vector.shape_cast %tmp_acc0 : vector<16xf32> to vector<4x4xf32>
        %tmp6 = vector.multi_reduction <add>, %tmp5, %tmp4 [0] : vector<4x4xf32> to vector<4xf32>
        affine.vector_store %tmp6, %spad1[%const0] : memref<512xf32, 1>, vector<4xf32>
        memref.dma_start %spad1[%const0], %out_ptr0[%index0], %const5, %alloc1[%const0], %const0, %const1 : memref<512xf32, 1>, memref<512xf32>, memref<1xi32> {dram_stride = [1], sram_stride = [1], padding = 0}
    } {outer_loop=true}
    return
}
